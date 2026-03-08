#!/usr/bin/env python3
"""
Runner script that starts Streamlit and creates a public tunnel.
Tries Cloudflare Tunnel first, falls back to ngrok if unavailable.
"""

import subprocess
import sys
import time
import re
import os
import signal
from pathlib import Path

STREAMLIT_PORT = 8501
STREAMLIT_APP = "app.py"

def check_command_exists(cmd):
    """Check if a command exists in PATH"""
    try:
        subprocess.run([cmd, "--version"], 
                      capture_output=True, 
                      check=True,
                      timeout=5)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return False

def start_streamlit():
    """Start Streamlit in the background"""
    print("🚀 Starting Streamlit...")
    process = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", STREAMLIT_APP, 
         "--server.port", str(STREAMLIT_PORT),
         "--server.headless", "true"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    # Wait a bit for Streamlit to start
    time.sleep(3)
    
    # Check if process is still running
    if process.poll() is not None:
        stderr = process.stderr.read() if process.stderr else ""
        print(f"❌ Streamlit failed to start: {stderr}")
        sys.exit(1)
    
    print(f"✅ Streamlit started on port {STREAMLIT_PORT}")
    return process

def start_cloudflare_tunnel():
    """Start Cloudflare Tunnel and extract URL"""
    print("🌐 Starting Cloudflare Tunnel...")
    
    try:
        process = subprocess.Popen(
            ["cloudflared", "tunnel", "--url", f"http://localhost:{STREAMLIT_PORT}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        
        # Read output line by line to find URL
        url = None
        timeout = 30
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            line = process.stdout.readline()
            if not line:
                if process.poll() is not None:
                    break
                time.sleep(0.1)
                continue
            
            print(line.strip())
            
            # Look for trycloudflare.com URL
            match = re.search(r'https://[a-z0-9-]+\.trycloudflare\.com', line)
            if match:
                url = match.group(0)
                break
        
        if url:
            print("\n" + "="*60)
            print("🌍 PUBLIC URL (copy and paste in browser):")
            print(f"   {url}")
            print("="*60 + "\n")
            return process, url
        else:
            print("⚠️  Could not extract Cloudflare URL from output")
            process.terminate()
            process.wait(timeout=5)
            return None, None
            
    except FileNotFoundError:
        print("❌ cloudflared not found in PATH")
        return None, None
    except Exception as e:
        print(f"❌ Error starting Cloudflare Tunnel: {e}")
        return None, None

def start_ngrok_tunnel():
    """Start ngrok tunnel using pyngrok"""
    print("🌐 Starting ngrok tunnel...")
    
    try:
        from pyngrok import ngrok
        
        # Start tunnel
        tunnel = ngrok.connect(STREAMLIT_PORT, "http")
        url = tunnel.public_url
        
        print("\n" + "="*60)
        print("🌍 PUBLIC URL (copy and paste in browser):")
        print(f"   {url}")
        print("="*60 + "\n")
        
        return tunnel, url
        
    except ImportError:
        print("❌ pyngrok not installed. Installing...")
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "pyngrok"], 
                         check=True)
            from pyngrok import ngrok
            tunnel = ngrok.connect(STREAMLIT_PORT, "http")
            url = tunnel.public_url
            
            print("\n" + "="*60)
            print("🌍 PUBLIC URL (copy and paste in browser):")
            print(f"   {url}")
            print("="*60 + "\n")
            
            return tunnel, url
        except Exception as e:
            print(f"❌ Failed to install/use pyngrok: {e}")
            return None, None
    except Exception as e:
        print(f"❌ Error starting ngrok tunnel: {e}")
        return None, None

def main():
    """Main function"""
    print("="*60)
    print("⚡ Energy Anomaly Explorer - Public URL Generator")
    print("="*60 + "\n")
    
    # Change to script directory
    script_dir = Path(__file__).parent
    os.chdir(script_dir)
    
    # Start Streamlit
    streamlit_process = start_streamlit()
    
    # Try Cloudflare Tunnel first
    tunnel_process = None
    tunnel_obj = None
    url = None
    
    if check_command_exists("cloudflared"):
        tunnel_process, url = start_cloudflare_tunnel()
    
    # Fallback to ngrok
    if not url:
        print("\n⚠️  Cloudflare Tunnel unavailable, trying ngrok...")
        tunnel_obj, url = start_ngrok_tunnel()
    
    if not url:
        print("\n❌ Failed to create tunnel. Streamlit is running locally at:")
        print(f"   http://localhost:{STREAMLIT_PORT}")
        print("\nTo create a tunnel manually:")
        print("   1. Install cloudflared: https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/")
        print("   2. Or install pyngrok: pip install pyngrok")
        print("   3. Then run this script again")
        print("\nPress Ctrl+C to stop Streamlit...")
        
        try:
            streamlit_process.wait()
        except KeyboardInterrupt:
            streamlit_process.terminate()
        sys.exit(1)
    
    # Keep running until interrupted
    print("✅ Dashboard is running!")
    print("📝 Press Ctrl+C to stop the server and tunnel\n")
    
    try:
        if tunnel_process:
            tunnel_process.wait()
        else:
            # For ngrok, keep the process alive
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n🛑 Shutting down...")
        
        # Stop tunnel
        if tunnel_process:
            tunnel_process.terminate()
            tunnel_process.wait(timeout=5)
        if tunnel_obj:
            try:
                from pyngrok import ngrok
                ngrok.disconnect(tunnel_obj.public_url)
                ngrok.kill()
            except:
                pass
        
        # Stop Streamlit
        streamlit_process.terminate()
        streamlit_process.wait(timeout=5)
        
        print("✅ Shutdown complete")

if __name__ == "__main__":
    main()

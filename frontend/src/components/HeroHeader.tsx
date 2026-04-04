import { motion } from 'framer-motion';
import { Zap } from 'lucide-react';

export default function HeroHeader() {
  return (
    <div className="relative hidden text-center py-10 px-4 md:block">
      <motion.div
        initial={{ opacity: 0, scale: 0.8 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.5 }}
        className="relative"
      >
        {/* Main Logo */}
        <div className="relative inline-block">
          <div className="flex items-center justify-center gap-4 mb-2">
            {/* Icon */}
            <motion.div
              animate={{ 
                rotate: [0, -5, 5, -5, 0],
                scale: [1, 1.1, 1]
              }}
              transition={{ 
                duration: 2,
                repeat: Infinity,
                repeatDelay: 3
              }}
              className="p-3 bg-gradient-to-br from-cyan-500 via-blue-500 to-purple-500 rounded-xl"
            >
              <Zap className="w-10 h-10 text-white" fill="white" />
            </motion.div>
          </div>

          {/* Text */}
          <div className="space-y-1">
            {/* ENERGY with anomaly on 'E' and 'R' */}
            <div className="flex items-center justify-center text-6xl tracking-tight">
              <motion.span
                animate={{ 
                  x: [0, -2, 2, -1, 0],
                  textShadow: [
                    '0 0 0px rgba(0,255,255,0)',
                    '2px 0 10px rgba(0,255,255,0.8), -2px 0 10px rgba(255,0,255,0.8)',
                    '0 0 0px rgba(0,255,255,0)'
                  ]
                }}
                transition={{ 
                  duration: 0.3,
                  repeat: Infinity,
                  repeatDelay: 4,
                  repeatType: "reverse"
                }}
                className="text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-cyan-600"
              >
                E
              </motion.span>
              <span className="text-white">N</span>
              <span className="text-white">E</span>
              <motion.span
                animate={{ 
                  y: [0, -3, 3, -2, 0],
                  rotate: [0, -2, 2, 0],
                  color: [
                    'rgb(255, 255, 255)',
                    'rgb(34, 211, 238)',
                    'rgb(255, 255, 255)'
                  ]
                }}
                transition={{ 
                  duration: 0.4,
                  repeat: Infinity,
                  repeatDelay: 3.5,
                }}
                className="text-white"
              >
                R
              </motion.span>
              <span className="text-white">G</span>
              <span className="text-white">Y</span>
            </div>

            {/* ANOMALY with anomaly effects on 'A', 'O', and 'Y' */}
            <div className="flex items-center justify-center text-6xl tracking-tight">
              <motion.span
                animate={{ 
                  scale: [1, 1.15, 0.95, 1],
                  color: [
                    'rgb(255, 255, 255)',
                    'rgb(239, 68, 68)',
                    'rgb(255, 255, 255)'
                  ]
                }}
                transition={{ 
                  duration: 0.5,
                  repeat: Infinity,
                  repeatDelay: 2.5,
                }}
                className="text-white"
              >
                A
              </motion.span>
              <span className="text-white">N</span>
              <motion.span
                animate={{ 
                  x: [0, 3, -3, 0],
                  opacity: [1, 0.7, 1],
                  textShadow: [
                    '0 0 0px rgba(255,0,0,0)',
                    '0 0 20px rgba(255,0,0,0.6)',
                    '0 0 0px rgba(255,0,0,0)'
                  ]
                }}
                transition={{ 
                  duration: 0.3,
                  repeat: Infinity,
                  repeatDelay: 3,
                }}
                className="text-white"
              >
                O
              </motion.span>
              <span className="text-white">M</span>
              <span className="text-white">A</span>
              <span className="text-white">L</span>
              <motion.span
                animate={{ 
                  y: [0, -4, 0],
                  rotate: [0, 5, -5, 0],
                  textShadow: [
                    '0 0 0px rgba(168,85,247,0)',
                    '0 0 15px rgba(168,85,247,0.8)',
                    '0 0 0px rgba(168,85,247,0)'
                  ]
                }}
                transition={{ 
                  duration: 0.4,
                  repeat: Infinity,
                  repeatDelay: 2,
                }}
                className="text-transparent bg-clip-text bg-gradient-to-b from-purple-400 to-white"
              >
                Y
              </motion.span>
            </div>

            {/* EXPLORER with anomaly on 'X' and 'E' at end */}
            <div className="flex items-center justify-center text-6xl tracking-tight">
              <span className="text-white">E</span>
              <motion.span
                animate={{ 
                  scaleX: [1, 1.2, 0.9, 1],
                  scaleY: [1, 0.8, 1.1, 1],
                }}
                transition={{ 
                  duration: 0.3,
                  repeat: Infinity,
                  repeatDelay: 4.5,
                }}
                className="text-transparent bg-clip-text bg-gradient-to-r from-yellow-400 to-orange-500"
              >
                X
              </motion.span>
              <span className="text-white">P</span>
              <span className="text-white">L</span>
              <span className="text-white">O</span>
              <span className="text-white">R</span>
              <motion.span
                animate={{ 
                  x: [0, 2, -2, 1, 0],
                  opacity: [1, 0.6, 1],
                  filter: [
                    'blur(0px)',
                    'blur(1px)',
                    'blur(0px)'
                  ]
                }}
                transition={{ 
                  duration: 0.2,
                  repeat: Infinity,
                  repeatDelay: 5,
                }}
                className="text-white"
              >
                E
              </motion.span>
              <span className="text-white">R</span>
            </div>
          </div>

          {/* Glitch overlay effect */}
          <motion.div
            animate={{ 
              opacity: [0, 0.3, 0],
            }}
            transition={{ 
              duration: 0.1,
              repeat: Infinity,
              repeatDelay: 6,
            }}
            className="absolute inset-0 bg-gradient-to-r from-cyan-500/20 to-purple-500/20 blur-xl"
          />
        </div>

        {/* Subtitle */}
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.5 }}
          className="mt-6 text-slate-400 text-sm tracking-wide italic"
        >
          Advanced anomaly detection for building energy load profiles
        </motion.p>
      </motion.div>
    </div>
  );
}

import { useRef, type ReactNode } from 'react';
import { X } from 'lucide-react';

const REPO = 'https://github.com/Taulark/Energy-Anomaly-Explorer';

function FooterLink({
  children,
  onClick,
  href,
}: {
  children: ReactNode;
  onClick?: () => void;
  href?: string;
}) {
  if (href) {
    return (
      <a
        href={href}
        className="text-gray-500 underline-offset-2 transition-colors hover:text-indigo-300 hover:underline"
        target={href.startsWith('http') ? '_blank' : undefined}
        rel={href.startsWith('http') ? 'noreferrer' : undefined}
      >
        {children}
      </a>
    );
  }
  return (
    <button
      type="button"
      onClick={onClick}
      className="text-gray-500 underline-offset-2 transition-colors hover:text-indigo-300 hover:underline"
    >
      {children}
    </button>
  );
}

export default function SiteFooter() {
  const year = new Date().getFullYear();
  const aboutRef = useRef<HTMLDialogElement>(null);
  const legalRef = useRef<HTMLDialogElement>(null);

  const scrollHome = () => {
    document.getElementById('app-top')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  const dialogClass =
    'w-[min(100%,26rem)] max-h-[85dvh] overflow-y-auto rounded-xl border border-[#2d2d44] bg-[#1a1a2e] p-6 text-left text-sm text-gray-300 shadow-2xl [&::backdrop]:bg-black/65';

  return (
    <>
      <footer className="mt-10 border-t border-[#2d2d44]/70 px-4 py-8 md:mt-12 md:px-6">
        <div className="mx-auto flex max-w-6xl flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <p className="text-center text-xs text-gray-600 md:text-left">
            © {year} Energy Anomaly Explorer. Educational / demonstration tool for building load anomaly
            analysis.
          </p>
          <nav
            className="flex flex-wrap items-center justify-center gap-x-4 gap-y-2 text-xs md:justify-end"
            aria-label="Site"
          >
            <FooterLink onClick={scrollHome}>Home</FooterLink>
            <FooterLink onClick={() => aboutRef.current?.showModal()}>About</FooterLink>
            <FooterLink href={REPO}>Source</FooterLink>
            <FooterLink href={`${REPO}/issues`}>Contact</FooterLink>
            <FooterLink onClick={() => legalRef.current?.showModal()}>Terms & Privacy</FooterLink>
          </nav>
        </div>
      </footer>

      <dialog ref={aboutRef} className={dialogClass}>
        <div className="mb-4 flex items-start justify-between gap-3">
          <h2 className="text-base font-semibold text-white">About</h2>
          <button
            type="button"
            className="rounded-lg p-1 text-gray-500 hover:bg-[#2d2d44] hover:text-white"
            aria-label="Close"
            onClick={() => aboutRef.current?.close()}
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        <p className="mb-3 leading-relaxed text-gray-400">
          Energy Anomaly Explorer helps you explore hourly building energy use, compare it to weather-driven
          baselines, and highlight statistically unusual hours using regression residuals and z-scores.
        </p>
        <p className="mb-6 text-xs text-gray-500">
          Sample data is sourced from public buildings datasets (e.g. OpenEI); uploads stay under your
          control and are sent only to this app&apos;s backend for processing.
        </p>
        <form method="dialog" className="flex justify-end">
          <button
            type="submit"
            className="rounded-lg bg-indigo-600 px-4 py-2 text-xs font-medium text-white hover:bg-indigo-500"
          >
            Close
          </button>
        </form>
      </dialog>

      <dialog ref={legalRef} className={dialogClass}>
        <div className="mb-4 flex items-start justify-between gap-3">
          <h2 className="text-base font-semibold text-white">Terms & Privacy</h2>
          <button
            type="button"
            className="rounded-lg p-1 text-gray-500 hover:bg-[#2d2d44] hover:text-white"
            aria-label="Close"
            onClick={() => legalRef.current?.close()}
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="space-y-3 text-xs leading-relaxed text-gray-400">
          <p>
            This application is provided as-is for research, coursework, and demonstration. It is not a
            substitute for professional energy auditing, M&amp;V, or compliance advice.
          </p>
          <p>
            Do not upload data you are not allowed to share. If you use production or tenant data, ensure you
            have appropriate consent, retention policies, and security reviews in place.
          </p>
          <p>
            Operators may log technical metadata (e.g. errors, request timing) required to run the service. We
            do not sell data; see your deployment&apos;s privacy policy for specifics.
          </p>
        </div>
        <form method="dialog" className="mt-6 flex justify-end">
          <button
            type="submit"
            className="rounded-lg bg-indigo-600 px-4 py-2 text-xs font-medium text-white hover:bg-indigo-500"
          >
            Close
          </button>
        </form>
      </dialog>
    </>
  );
}

import React, { useEffect, useRef, useState, useLayoutEffect } from 'react';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { ArrowRight, ChevronRight, CheckCircle2, Circle, LayoutGrid, Terminal, Cpu, ShieldAlert, Globe, Lock } from 'lucide-react';

gsap.registerPlugin(ScrollTrigger);

// --- Component A: Floating Navbar ---
const Navbar = () => {
  const [scrolled, setScrolled] = useState(false);
  
  useEffect(() => {
    const handleScroll = () => setScrolled(window.scrollY > 80);
    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  return (
    <nav className={`fixed top-6 left-1/2 -translate-x-1/2 z-[100] transition-all duration-500 rounded-[2rem] px-8 py-4 flex items-center gap-12
      ${scrolled ? 'glass-dark border border-white/10 shadow-2xl scale-100' : 'bg-transparent text-white border border-transparent scale-105'}
    `}>
      <div className="font-display font-bold text-xl tracking-tight text-white flex items-center gap-2">
        <div className="w-5 h-5 rounded-full bg-accent animate-pulse shadow-[0_0_15px_rgba(0,113,227,0.5)]"></div>
        247<span className="font-light">Profits</span>
      </div>
      <div className="hidden md:flex gap-8 text-sm font-medium opacity-80 text-white">
        <a href="#features" className="hover:-translate-y-0.5 transition-transform hover:text-white">Protocol</a>
        <a href="#philosophy" className="hover:-translate-y-0.5 transition-transform hover:text-white">Philosophy</a>
        <a href="#system" className="hover:-translate-y-0.5 transition-transform hover:text-white">System</a>
      </div>
      <button className="bg-white text-primary px-6 py-2 rounded-full font-semibold text-sm hover:scale-105 transition-transform">
        Log In
      </button>
    </nav>
  );
};

// --- Component B: The Opening Shot ---
const Hero = () => {
  const container = useRef(null);
  
  useLayoutEffect(() => {
    let ctx = gsap.context(() => {
      gsap.from(".hero-text", {
        y: 40, opacity: 0, duration: 1.2, stagger: 0.15, ease: "power3.out", delay: 0.2
      });
      gsap.from(".hero-btn", {
        scale: 0.9, opacity: 0, duration: 1, ease: "back.out(1.7)", delay: 0.8
      });
    }, container);
    return () => ctx.revert();
  }, []);

  return (
    <section ref={container} className="relative h-[100dvh] w-full flex flex-col justify-end pb-32 px-8 md:px-24 bg-primary text-white overflow-hidden">
      <div className="absolute inset-0 bg-[url('https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?q=80&w=2564&auto=format&fit=crop')] bg-cover bg-center opacity-40 mix-blend-luminosity"></div>
      <div className="absolute inset-0 bg-gradient-to-t from-primary via-primary/80 to-transparent"></div>
      
      <div className="relative z-10 max-w-5xl">
        <h1 className="hero-text text-5xl md:text-8xl font-display font-bold tracking-tighter leading-[0.9] mb-4">
          Autonomous intelligence meets
        </h1>
        <h2 className="hero-text text-6xl md:text-9xl font-drama italic text-transparent bg-clip-text bg-gradient-to-r from-gray-200 to-gray-500 mb-8 pb-4">
          7-Figure Scale.
        </h2>
        <p className="hero-text text-lg md:text-xl text-gray-400 max-w-2xl mb-10 font-medium">
          The ultimate Amazon FBA SAAS infrastructure. Stop guessing with manual sourcing. Deploy the absolute pinnacle of competitive retail intelligence.
        </p>
        <button className="hero-btn group relative overflow-hidden bg-accent text-white px-10 py-5 rounded-[2rem] font-bold text-lg flex items-center gap-3 transition-all duration-500 hover:scale-[1.03] shadow-[0_20px_40px_rgba(0,113,227,0.3)]">
          <span className="relative z-10 flex items-center gap-3">Sign up / Log in <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" /></span>
        </button>
      </div>
    </section>
  );
};

// --- Component C: Features (Functional Micro-UIs) ---

const DiagnosticShuffler = () => {
  const [cards, setCards] = useState([
    { id: 1, label: "Neural Web Scraping", risk: "Low", status: "Active", bg: "bg-surface text-primary" },
    { id: 2, label: "Dynamic ROI Math", risk: "None", status: "Processing", bg: "bg-gray-100 text-gray-800" },
    { id: 3, label: "Real-time ASIN Matching", risk: "Med", status: "Scanning...", bg: "bg-gray-200 text-gray-700" }
  ]);

  useEffect(() => {
    const interval = setInterval(() => {
      setCards(prev => {
        const newCards = [...prev];
        const last = newCards.pop();
        newCards.unshift(last);
        return newCards;
      });
    }, 3000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="relative h-64 flex items-center justify-center p-6 bg-gray-50 rounded-[2rem] border border-gray-100 shadow-inner">
      <div className="absolute top-6 left-6 flex items-center gap-2">
        <div className="w-2 h-2 rounded-full bg-accent animate-pulse"></div>
        <span className="text-xs font-mono font-bold tracking-widest text-gray-400">AI-POWERED SOURCING</span>
      </div>
      {cards.map((c, i) => (
        <div key={c.id} className={`absolute w-full max-w-xs p-6 rounded-[1.5rem] shadow-xl transition-all duration-700 ${c.bg}`}
          style={{ transform: `translateY(${i * 12}px) scale(${1 - i * 0.05})`, zIndex: 10 - i, opacity: 1 - i * 0.2 }}>
          <div className="flex justify-between items-start mb-6">
            <Cpu className="w-6 h-6 opacity-60" />
            <span className="text-xs font-bold px-3 py-1 bg-black/5 rounded-full">{c.status}</span>
          </div>
          <h4 className="font-bold text-lg mb-1">{c.label}</h4>
          <p className="text-xs opacity-60 font-mono">Confidence &gt; 98.4%</p>
        </div>
      ))}
    </div>
  );
}

const TelemetryTypewriter = () => {
  const [text, setText] = useState('');
  const fullText = "INITIATING 7-FIGURE INFRASTRUCTURE...\n> LOAD BALANCING 5,000 REQUESTS/SEC\n> PARSING RETAILER ARBITRAGE DOM\n> ROI CALCULATED: 42.8% VERIFIED\n> SYSTEM HEALTH: 100% OPERATIONAL";
  
  useEffect(() => {
    let index = 0;
    const interval = setInterval(() => {
      setText(fullText.slice(0, index));
      index++;
      if(index > fullText.length) index = 0; // loop for demo
    }, 80);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="relative h-64 p-6 bg-[#0A0A0A] rounded-[2rem] border border-gray-800 shadow-2xl flex flex-col font-mono text-sm text-green-400 overflow-hidden">
      <div className="absolute top-4 right-4 flex items-center gap-2 opacity-50">
        <Terminal className="w-4 h-4" />
        <span className="text-xs">CLUSTER_01</span>
      </div>
      <div className="mt-8 flex-1">
        <pre className="whitespace-pre-wrap leading-relaxed">
          {text}<span className="inline-block w-2 h-4 bg-green-400 animate-pulse align-middle ml-1"></span>
        </pre>
      </div>
    </div>
  );
}

const CursorScheduler = () => {
  const [activeDay, setActiveDay] = useState(0);
  const days = ['S','M','T','W','T','F','S'];

  useEffect(() => {
    const interval = setInterval(() => {
      setActiveDay(p => (p + 1) % 7);
    }, 1500);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="relative h-64 p-6 bg-surface rounded-[2rem] border border-gray-100 shadow-xl flex flex-col justify-center items-center">
      <div className="w-full mb-6 text-center">
        <h4 className="font-display font-bold text-xl">$50M+ Generated</h4>
        <p className="text-xs text-gray-400 mt-1">Automated compounding workflow</p>
      </div>
      <div className="flex gap-2 w-full justify-center relative">
        {days.map((d, i) => (
          <div key={i} className={`w-10 h-10 rounded-xl flex items-center justify-center font-bold text-sm transition-all duration-300
            ${i === activeDay ? 'bg-accent text-white scale-110 shadow-lg' : 'bg-gray-100 text-gray-400'}`}>
            {d}
          </div>
        ))}
        <svg className="absolute w-6 h-6 text-black transition-all duration-500 ease-out z-10" 
             style={{ left: `calc(50% - 150px + ${activeDay * 48}px)`, top: '24px' }}
             fill="currentColor" viewBox="0 0 24 24">
          <path d="M4 2L20 10L13 13L16 22L13.5 23L11 15L6 19V2Z" />
        </svg>
      </div>
    </div>
  );
}

const Features = () => {
  const container = useRef(null);

  useLayoutEffect(() => {
    let ctx = gsap.context(() => {
      gsap.from(".feature-card", {
        scrollTrigger: { trigger: container.current, start: "top 70%" },
        y: 60, opacity: 0, duration: 1, stagger: 0.2, ease: "power3.out"
      });
    }, container);
    return () => ctx.revert();
  }, []);

  return (
    <section id="features" ref={container} className="py-32 px-8 max-w-7xl mx-auto">
      <div className="mb-20">
        <h2 className="text-5xl font-display font-bold tracking-tight mb-4 text-primary">Operate at <span className="font-drama italic font-normal text-gray-500">Enterprise</span> Scale</h2>
        <p className="text-xl text-muted max-w-2xl">Stop relying on public tools. Build unbreakable sourcing workflows with our private infrastructure.</p>
      </div>
      <div className="grid md:grid-cols-3 gap-8">
        <div className="feature-card">
          <DiagnosticShuffler />
          <h3 className="text-xl font-bold mt-8 mb-2">AI-Powered Sourcing</h3>
          <p className="text-muted text-sm">Our neural web scrapers find profitable disparities before the market reacts.</p>
        </div>
        <div className="feature-card">
          <TelemetryTypewriter />
          <h3 className="text-xl font-bold mt-8 mb-2">7-Figure Infrastructure</h3>
          <p className="text-muted text-sm">Serverless execution environments designed to handle millions of ASINs concurrently.</p>
        </div>
        <div className="feature-card">
          <CursorScheduler />
          <h3 className="text-xl font-bold mt-8 mb-2">Proven to $50M+</h3>
          <p className="text-muted text-sm">The exact same logic and systems that have generated over $50,000,000 in Amazon FBA revenue.</p>
        </div>
      </div>
    </section>
  );
};

// --- Component D: Philosophy ---
const Philosophy = () => {
  const container = useRef(null);
  
  useLayoutEffect(() => {
    let ctx = gsap.context(() => {
      gsap.from(".phil-text-1", {
        scrollTrigger: { trigger: container.current, start: "top 60%" },
        opacity: 0, x: -30, duration: 1
      });
      gsap.from(".phil-text-2", {
        scrollTrigger: { trigger: container.current, start: "top 50%" },
        opacity: 0, y: 40, duration: 1.2, ease: "power3.out", delay: 0.2
      });
    }, container);
    return () => ctx.revert();
  }, []);

  return (
    <section id="philosophy" ref={container} className="relative py-48 px-8 bg-primary text-white overflow-hidden rounded-[4rem] mx-4 md:mx-12 my-24">
      <div className="absolute inset-0 bg-[url('https://images.unsplash.com/photo-1541888031542-a292728db940?q=80&w=2670&auto=format&fit=crop')] bg-cover bg-center opacity-[0.15] mix-blend-screen scale-110 -z-0"></div>
      <div className="relative z-10 max-w-4xl mx-auto flex flex-col gap-12">
        <p className="phil-text-1 text-2xl font-light text-gray-400">
          Most FBA tools focus on: <span className="font-mono">generic scraping</span> and shared data lakes.
        </p>
        <p className="phil-text-2 text-5xl md:text-7xl font-drama italic leading-tight">
          We focus on: <span className="text-accent underline decoration-1 underline-offset-8">autonomous dominance</span> and private intelligence.
        </p>
      </div>
    </section>
  );
};

// --- Component E: Protocol (Sticky Stacking) ---
const Protocol = () => {
  return (
    <section id="system" className="py-24 px-8 max-w-5xl mx-auto flex flex-col gap-12">
      <div className="sticky top-32 p-12 bg-surface rounded-[3rem] shadow-[0_30px_60px_rgba(0,0,0,0.05)] border border-gray-100 flex flex-col md:flex-row gap-12 items-center origin-top transition-transform duration-500" style={{ zIndex: 1, top: '100px' }}>
        <div className="w-16 h-16 rounded-2xl bg-black text-white flex items-center justify-center font-mono text-xl font-bold shrink-0 shadow-2xl">01</div>
        <div className="flex-1">
          <h3 className="text-3xl font-display font-bold mb-4">Ingest & Map</h3>
          <p className="text-lg text-muted">Initialize the autonomous sweep across 100+ retail nodes. We parse millions of SKUs, cataloging price disparities in real-time.</p>
        </div>
        <div className="w-48 h-48 rounded-full border border-gray-200 relative animate-[spin_20s_linear_infinite] shrink-0 hidden md:block">
          <div className="absolute top-0 left-1/2 w-4 h-4 bg-accent rounded-full -translate-x-1/2 -translate-y-1/2 blur-[2px]"></div>
          <div className="absolute top-1/2 right-0 w-3 h-3 bg-primary rounded-full translate-x-1/2 -translate-y-1/2"></div>
        </div>
      </div>

      <div className="sticky top-32 p-12 bg-primary text-white rounded-[3rem] shadow-[0_30px_60px_rgba(0,0,0,0.2)] flex flex-col md:flex-row gap-12 items-center origin-top transition-transform duration-500" style={{ zIndex: 2, top: '140px' }}>
        <div className="w-16 h-16 rounded-2xl bg-white text-primary flex items-center justify-center font-mono text-xl font-bold shrink-0 shadow-2xl">02</div>
        <div className="flex-1">
          <h3 className="text-3xl font-display font-bold mb-4">AI Verification</h3>
          <p className="text-lg text-gray-400">Our models don't just guess. We cross-reference buybox history, inbound velocity, and hazardous materials logic to verify pure margin.</p>
        </div>
        <div className="w-48 h-48 overflow-hidden rounded-2xl bg-white/5 relative shrink-0 hidden md:flex flex-col gap-2 p-4">
           {[...Array(6)].map((_,i) => <div key={i} className="h-4 bg-white/10 rounded-full w-full overflow-hidden relative"><div className="absolute inset-y-0 left-0 bg-accent w-full -translate-x-full animate-[slide_3s_ease-in-out_infinite]" style={{animationDelay: `${i*0.2}s`}}></div></div>)}
        </div>
      </div>

      <div className="sticky top-32 p-12 bg-accent text-white rounded-[3rem] shadow-[0_30px_60px_rgba(0,113,227,0.3)] flex flex-col md:flex-row gap-12 items-center origin-top" style={{ zIndex: 3, top: '180px' }}>
        <div className="w-16 h-16 rounded-2xl bg-white text-accent flex items-center justify-center font-mono text-xl font-bold shrink-0 shadow-2xl">03</div>
        <div className="flex-1">
          <h3 className="text-3xl font-display font-bold mb-4">Extract Profits</h3>
          <p className="text-lg opacity-90">Export the verified ASIN manifest, execute your purchasing strategy, and ship to FBA perfectly optimized.</p>
        </div>
        <div className="w-48 h-48 rounded-3xl bg-white/10 flex items-center justify-center shrink-0 hidden md:flex">
          <ShieldAlert className="w-20 h-20 opacity-80" />
        </div>
      </div>
    </section>
  );
};

// --- Component F: Footer ---
const Footer = () => {
  return (
    <footer className="bg-primary text-white pt-24 pb-12 px-8 rounded-t-[4rem] mt-32">
      <div className="max-w-7xl mx-auto flex flex-col items-center text-center">
        <h2 className="text-5xl md:text-7xl font-display font-bold mb-12">Initialize The System.</h2>
        <button className="bg-white text-primary px-12 py-6 rounded-full font-bold text-xl mb-32 hover:scale-105 transition-transform shadow-[0_0_40px_rgba(255,255,255,0.2)]">
          Launch Enterprise Dashboard
        </button>
        
        <div className="w-full flex flex-col md:flex-row justify-between items-center border-t border-white/10 pt-12 text-sm text-gray-500 font-medium font-mono">
          <div className="flex items-center gap-3 mb-6 md:mb-0">
            <div className="w-3 h-3 bg-green-500 rounded-full animate-pulse"></div>
            SYSTEM OPERATIONAL
          </div>
          <div className="flex gap-8">
            <a href="#" className="hover:text-white transition-colors">Documentation</a>
            <a href="#" className="hover:text-white transition-colors">Terms of Service</a>
            <a href="#" className="hover:text-white transition-colors">Privacy Protocol</a>
          </div>
        </div>
      </div>
    </footer>
  );
};

// --- Main App ---
function App() {
  return (
    <div className="min-h-screen selection:bg-accent selection:text-white">
      <Navbar />
      <Hero />
      <Features />
      <Philosophy />
      <Protocol />
      <Footer />
    </div>
  );
}

export default App;

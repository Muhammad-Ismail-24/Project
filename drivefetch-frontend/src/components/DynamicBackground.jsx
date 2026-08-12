import { useEffect } from 'react';
import { motion, useScroll, useTransform, useMotionValue, useSpring } from 'framer-motion';

/**
 * DynamicBackground
 *
 * Fixed full-screen layer with 4 SVG pattern layers.
 * Uses Framer Motion's useScroll() + useTransform() to
 * crossfade layers based on scrollYProgress (0 → 1):
 *
 *   0.00 → 0.25  Layer 1 (Topo) visible, fading out
 *   0.15 → 0.50  Layer 2 (Waves) fading in then out
 *   0.40 → 0.75  Layer 3 (Grid) fading in then out
 *   0.60 → 1.00  Layer 4 (Gauges) fading in, stays
 *
 * Overlapping ranges ensure smooth crossfades with no dead zones.
 */

const PATTERN_COLOR = '#D4D4D4';
const STROKE = 1.5;
const LABEL_COLOR = '#D8D8D8';

/* ═══════════════════════════════════════════════════════
   SVG PATTERN DEFINITIONS
   ═══════════════════════════════════════════════════════ */

function TopoPattern() {
  return (
    <svg width="100%" height="100%" viewBox="0 0 800 600" preserveAspectRatio="xMidYMid slice">
      <g fill="none" stroke={PATTERN_COLOR} strokeWidth={STROKE}>
        <path d="M400,300 Q480,220 520,280 Q560,340 500,380 Q440,420 380,370 Q320,320 400,300Z" />
        <path d="M400,300 Q500,190 560,270 Q620,350 530,410 Q440,470 350,390 Q260,310 400,300Z" />
        <path d="M400,300 Q530,160 600,260 Q670,360 560,440 Q450,520 320,410 Q190,300 400,300Z" />
        <path d="M400,300 Q560,120 650,240 Q740,360 590,470 Q440,580 280,430 Q120,280 400,300Z" />
        <path d="M400,300 Q590,80 700,220 Q810,360 620,500 Q430,640 240,450 Q50,260 400,300Z" />
        <path d="M200,150 Q250,100 300,140 Q350,180 290,210 Q230,240 200,150Z" />
        <path d="M200,150 Q270,70 340,130 Q410,190 310,240 Q210,290 170,130Z" />
        <path d="M200,150 Q290,40 380,120 Q470,200 330,270 Q190,340 140,110Z" />
        <path d="M620,120 Q660,90 690,120 Q720,150 680,170 Q640,190 620,120Z" />
        <path d="M620,120 Q680,60 720,110 Q760,160 700,200 Q640,240 590,100Z" />
        <path d="M150,450 Q200,410 250,440 Q300,470 240,500 Q180,530 150,450Z" />
        <path d="M150,450 Q220,390 290,430 Q360,470 270,520 Q180,570 120,430Z" />
        <path d="M150,450 Q240,370 330,420 Q420,470 300,540 Q180,610 90,410Z" />
        <path d="M680,420 Q720,390 750,420 Q780,450 740,470 Q700,490 680,420Z" />
        <path d="M680,420 Q740,370 780,410 Q820,450 760,490 Q700,530 650,400Z" />
      </g>
    </svg>
  );
}

function WavePattern() {
  return (
    <svg width="100%" height="100%" viewBox="0 0 800 600" preserveAspectRatio="xMidYMid slice">
      <g fill="none" stroke={PATTERN_COLOR} strokeWidth={STROKE}>
        <polyline points="0,300 50,300 50,260 100,260 100,290 150,290 150,240 200,240 200,270 250,270 250,220 300,220 300,260 350,260 350,200 400,200 400,250 450,250 450,190 500,190 500,230 550,230 550,180 600,180 600,220 650,220 650,170 700,170 700,210 750,210 750,160 800,160" />
        <polyline points="0,380 50,380 50,350 100,350 100,370 150,370 150,330 200,330 200,360 250,360 250,310 300,310 300,350 350,350 350,290 400,290 400,340 450,340 450,280 500,280 500,320 550,320 550,270 600,270 600,310 650,310 650,260 700,260 700,300 750,300 750,250 800,250" />
        <polyline points="0,460 50,460 50,440 100,440 100,450 150,450 150,420 200,420 200,440 250,440 250,400 300,400 300,430 350,430 350,380 400,380 400,420 450,420 450,370 500,370 500,400 550,400 550,360 600,360 600,390 650,390 650,350 700,350 700,380 750,380 750,340 800,340" />
        <polyline points="0,180 40,180 40,150 90,150 90,170 140,170 140,130 200,130 200,160 260,160 260,120 320,120 320,150 380,150 380,110 440,110 440,140 500,140 500,100 560,100 560,130 620,130 620,95 680,95 680,120 740,120 740,85 800,85" strokeWidth="0.8" opacity="0.6" />
        <line x1="0" y1="500" x2="800" y2="500" strokeDasharray="4 6" />
        <line x1="0" y1="520" x2="800" y2="520" strokeDasharray="2 8" strokeWidth="0.6" />
        <line x1="30" y1="140" x2="30" y2="510" strokeDasharray="3 5" strokeWidth="0.5" />
        <line x1="770" y1="80" x2="770" y2="510" strokeDasharray="3 5" strokeWidth="0.5" />
        <circle cx="100" cy="260" r="3" fill={PATTERN_COLOR} />
        <circle cx="250" cy="220" r="3" fill={PATTERN_COLOR} />
        <circle cx="400" cy="200" r="3" fill={PATTERN_COLOR} />
        <circle cx="550" cy="180" r="3" fill={PATTERN_COLOR} />
        <circle cx="700" cy="170" r="3" fill={PATTERN_COLOR} />
        <circle cx="320" cy="120" r="2.5" fill={PATTERN_COLOR} />
        <circle cx="560" cy="100" r="2.5" fill={PATTERN_COLOR} />
      </g>
      <g fontFamily="'JetBrains Mono', monospace" fontSize="7" fill={LABEL_COLOR} letterSpacing="0.05em">
        <text x="105" y="252">[SIGNAL_PULL]</text>
        <text x="405" y="192">[SCRAPE_LATENCY: 0.12s]</text>
        <text x="555" y="172">[NODE_ACTIVE]</text>
        <text x="705" y="162">[FETCH_QUEUE: 3]</text>
        <text x="260" y="212">[PARSE_OK]</text>
        <text x="325" y="112">[YIELD: 94.2%]</text>
        <text x="42" y="496">[BASELINE_REF]</text>
        <text x="630" y="496">[T_AXIS: 0ms → 1200ms]</text>
      </g>
    </svg>
  );
}

function GridPattern() {
  return (
    <svg width="100%" height="100%" viewBox="0 0 800 600" preserveAspectRatio="xMidYMid slice">
      <defs>
        <pattern id="bg-smallGrid" width="20" height="20" patternUnits="userSpaceOnUse">
          <path d="M 20 0 L 0 0 0 20" fill="none" stroke={PATTERN_COLOR} strokeWidth="0.5" />
        </pattern>
        <pattern id="bg-largeGrid" width="100" height="100" patternUnits="userSpaceOnUse">
          <rect width="100" height="100" fill="url(#bg-smallGrid)" />
          <path d="M 100 0 L 0 0 0 100" fill="none" stroke={PATTERN_COLOR} strokeWidth={STROKE} />
        </pattern>
      </defs>
      <rect width="100%" height="100%" fill="url(#bg-largeGrid)" />
      <g stroke={PATTERN_COLOR} strokeWidth={STROKE}>
        <line x1="380" y1="280" x2="420" y2="280" />
        <line x1="400" y1="260" x2="400" y2="300" />
        <circle cx="400" cy="280" r="12" fill="none" />
        <line x1="580" y1="180" x2="620" y2="180" />
        <line x1="600" y1="160" x2="600" y2="200" />
        <circle cx="600" cy="180" r="8" fill="none" />
        <line x1="180" y1="420" x2="220" y2="420" />
        <line x1="200" y1="400" x2="200" y2="440" />
        <circle cx="200" cy="420" r="8" fill="none" />
        <line x1="120" y1="140" x2="150" y2="140" />
        <line x1="135" y1="125" x2="135" y2="155" />
        <circle cx="135" cy="140" r="6" fill="none" />
        <line x1="660" y1="460" x2="690" y2="460" />
        <line x1="675" y1="445" x2="675" y2="475" />
        <circle cx="675" cy="460" r="6" fill="none" />
      </g>
      <g fontFamily="'JetBrains Mono', monospace" fontSize="7" fill={LABEL_COLOR} letterSpacing="0.05em">
        <text x="415" y="275">[X: 42.08, Y: 108.92]</text>
        <text x="615" y="175">[X: 78.31, Y: 54.60]</text>
        <text x="205" y="415">[X: 12.50, Y: 162.40]</text>
        <text x="140" y="135">[X: 8.44, Y: 38.20]</text>
        <text x="695" y="455">[X: 91.72, Y: 188.00]</text>
      </g>
    </svg>
  );
}

function GaugePattern() {
  return (
    <svg width="100%" height="100%" viewBox="0 0 800 600" preserveAspectRatio="xMidYMid slice">
      <g fill="none" stroke={PATTERN_COLOR} strokeWidth={STROKE}>
        <path d="M200,400 A150,150 0 0,1 350,250" />
        <path d="M200,400 A180,180 0 0,1 380,220" />
        <path d="M200,400 A210,210 0 0,1 410,190" />
        <line x1="335" y1="252" x2="345" y2="242" />
        <line x1="300" y1="270" x2="308" y2="258" />
        <line x1="268" y1="300" x2="278" y2="290" />
        <line x1="248" y1="340" x2="260" y2="332" />
        <line x1="200" y1="400" x2="310" y2="275" strokeWidth="1.8" />
        <circle cx="200" cy="400" r="6" />
        <line x1="500" y1="150" x2="500" y2="450" strokeDasharray="6 4" />
        <line x1="550" y1="180" x2="550" y2="420" strokeDasharray="3 3" />
        <line x1="600" y1="200" x2="600" y2="400" strokeDasharray="6 4" />
        <line x1="650" y1="220" x2="650" y2="380" strokeDasharray="3 3" />
        <line x1="700" y1="240" x2="700" y2="360" strokeDasharray="6 4" />
        <line x1="480" y1="300" x2="720" y2="300" />
        <line x1="460" y1="350" x2="740" y2="350" strokeDasharray="2 4" />
        <line x1="500" y1="295" x2="500" y2="305" />
        <line x1="550" y1="295" x2="550" y2="305" />
        <line x1="600" y1="295" x2="600" y2="305" />
        <line x1="650" y1="295" x2="650" y2="305" />
        <line x1="700" y1="295" x2="700" y2="305" />
      </g>
    </svg>
  );
}

/* ═══════════════════════════════════════════════════════
   DYNAMIC BACKGROUND — Framer Motion scroll-linked
   ═══════════════════════════════════════════════════════ */

export default function DynamicBackground() {
  const { scrollYProgress } = useScroll();

  // Opacity crossfades
  const opacity1 = useTransform(scrollYProgress, [0, 0.2, 0.3], [1, 1, 0]);
  const opacity2 = useTransform(scrollYProgress, [0.15, 0.33, 0.50, 0.55], [0, 1, 1, 0]);
  const opacity3 = useTransform(scrollYProgress, [0.40, 0.55, 0.66, 0.75], [0, 1, 1, 0]);
  const opacity4 = useTransform(scrollYProgress, [0.60, 0.7, 1.0], [0, 1, 1]);



  // Mouse-Move Parallax Physics
  const mouseX = useMotionValue(0);
  const mouseY = useMotionValue(0);

  const springConfig = { stiffness: 50, damping: 30 };
  const smoothMouseX = useSpring(mouseX, springConfig);
  const smoothMouseY = useSpring(mouseY, springConfig);

  useEffect(() => {
    const handleMouseMove = (e) => {
      // Calculate mouse position relative to center of screen (-1 to 1)
      const x = (e.clientX / window.innerWidth - 0.5) * 2;
      const y = (e.clientY / window.innerHeight - 0.5) * 2;
      
      // Shift by a subtle amount (20px max)
      mouseX.set(x * 20);
      mouseY.set(y * 20);
    };

    window.addEventListener('mousemove', handleMouseMove);
    return () => window.removeEventListener('mousemove', handleMouseMove);
  }, [mouseX, mouseY]);

  const layers = [
    { Component: TopoPattern, opacity: opacity1 },
    { Component: WavePattern, opacity: opacity2 },
    { Component: GridPattern, opacity: opacity3 },
    { Component: GaugePattern, opacity: opacity4 },
  ];

  return (
    <div
      className="fixed inset-0 w-full h-full -z-10 bg-white pointer-events-none overflow-hidden"
      aria-hidden="true"
    >
      {layers.map(({ Component, opacity }, i) => (
        <motion.div
          key={i}
          className="absolute inset-0 will-change-transform"
          style={{ opacity, x: smoothMouseX, y: smoothMouseY }}
        >
          <Component />
        </motion.div>
      ))}
    </div>
  );
}

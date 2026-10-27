import { useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';
import SEO from '../components/SEO';
import SplitText from '../components/motion/SplitText';
import { buildAboutSchema } from '../config/seoSchemas';
import profilePic from '../assets/profile.jpeg';
import { Spinner } from '../components/ui/Loaders';
import { REPO_URL } from '../components/shell/navLinks';

/**
 * Single source for the FAQ. The accordion renders from this array AND the
 * FAQPage JSON-LD is generated from it, so the rich snippet never describes a
 * question that is not visibly on the page (Google's FAQ policy).
 */
const FAQS = [
  {
    q: 'How does DriveFetch calculate fair market value?',
    a: 'Our engine cross-references thousands of live listings, adjusting for mileage, condition, and local market trends to pinpoint the exact true value, eliminating seller inflation.',
  },
  {
    q: 'Are the vehicle listings real-time?',
    a: 'Yes. DriveFetch actively scrapes platforms like PakWheels, OLX, and Gari.pk the moment you execute a search to ensure zero stale data.',
  },
  {
    q: 'Does DriveFetch store my passwords?',
    a: 'Never. We utilize Google OAuth 2.0 for secure, frictionless authentication. We only store basic profile data and your saved preferences.',
  },
  {
    q: 'Why do some cars get flagged by the AI?',
    a: 'Our NLP models read between the lines of seller descriptions. If a seller claims "B2B genuine" but mentions "sides sprayed," the system immediately flags the contradiction.',
  },
  {
    q: 'Is DriveFetch free to use?',
    a: 'Yes. Our core matchmaking, scraping, and AI appraisal tools are currently completely free for standard market queries.',
  },
];

const STEPS = [
  { n: '01', t: 'Search 7 sites at once', d: 'PakWheels, OLX, Gari.pk, Drive.pk, FameWheels, AutoDeals and WiseWheels, in parallel.', code: 'scrapers/runner.py' },
  { n: '02', t: 'Clean up the names', d: 'Different spellings of the same make, model and trim become one car.', code: 'scrapers/normalizer.py' },
  { n: '03', t: 'Remove duplicates', d: 'One car posted on three sites shows once.', code: 'stage: aggregating' },
  { n: '04', t: 'Read the ad', d: 'An AI reviewer flags resprays, file problems and pressure tactics, with reasons.', code: 'agents/ReviewerAgent.py' },
  { n: '05', t: 'Check the price', d: 'Each car is compared with similar live ads.', code: 'agents/evaluator.py' },
];

const WEB3FORMS_KEY = 'e5b8198a-38e6-4ea5-b5fa-ade6ca15ce58';
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

export default function About() {
  const location = useLocation();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [message, setMessage] = useState('');
  const [tried, setTried] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSubmitted, setIsSubmitted] = useState(false);
  const [submitError, setSubmitError] = useState('');

  useEffect(() => {
    if (location.hash === '#contact') {
      setTimeout(() => document.getElementById('contact')?.scrollIntoView({ behavior: 'smooth' }), 50);
    }
  }, [location.hash]);

  const nameBad = tried && !name.trim();
  const emailBad = tried && !EMAIL_RE.test(email.trim());
  const msgBad = tried && !message.trim();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setTried(true);
    if (!name.trim() || !EMAIL_RE.test(email.trim()) || !message.trim()) return;
    setIsSubmitting(true);
    setSubmitError('');
    const formData = new FormData();
    formData.append('name', name.trim());
    formData.append('email', email.trim());
    formData.append('message', message.trim());
    formData.append('access_key', WEB3FORMS_KEY);
    try {
      const response = await fetch('https://api.web3forms.com/submit', { method: 'POST', body: formData });
      const data = await response.json();
      if (data.success) {
        setIsSubmitted(true);
      } else {
        console.error('Web3Forms error:', data.message);
        setSubmitError('Couldn’t send. Try again in a moment; your message is still here.');
      }
    } catch (error) {
      console.error('Network Error:', error);
      setSubmitError('Network error. Check your connection; your message is still here.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const reset = () => {
    setName(''); setEmail(''); setMessage(''); setTried(false); setIsSubmitted(false); setSubmitError('');
  };

  const fieldCls = (bad) => `w-full px-4 border-2 bg-transparent text-base outline-none focus:border-df-red ${bad ? 'border-df-red' : 'border-black dark:border-zinc-50'}`;

  return (
    <div className="w-full">
      <SEO
        title="About DriveFetch | Intelligent Car Discovery in Pakistan"
        description="How DriveFetch unifies the Pakistani used car market with multi-agent AI and real-time multi-platform search."
        path="/about"
        schema={buildAboutSchema(FAQS)}
      />

      {/* Problem / fix */}
      <section className="flex flex-wrap">
        <div className="flex-[1_1_520px] min-w-0 bg-black text-white px-5 sm:px-10 py-16 sm:py-20 flex flex-col gap-5">
          <span data-reveal="fade" className="font-mono text-[13px] font-semibold text-zinc-400">THE PROBLEM</span>
          <h1 className="df-display text-[length:clamp(56px,7.5vw,116px)]"><SplitText text="The market" className="block" /><SplitText text="is broken." className="block" start={2} /></h1>
          <p data-reveal style={{ '--rd': '300ms' }} className="max-w-[520px] text-[19px] leading-relaxed text-zinc-300">Buyers spend hours cross-checking listings, only to hit duplicate ads, fake pricing and hidden faults. Deciding well takes market knowledge most people don’t have.</p>
        </div>
        <div className="flex-[1_1_520px] min-w-0 bg-df-red text-white px-5 sm:px-10 py-16 sm:py-20 flex flex-col gap-5">
          <span data-reveal="fade" className="font-mono text-[13px] font-semibold">THE FIX</span>
          <h2 className="df-display text-[length:clamp(56px,7.5vw,116px)]"><SplitText text="Let the machine" className="block" delay={250} /><SplitText text="do the legwork." className="block text-black" start={3} delay={250} /></h2>
          <p data-reveal style={{ '--rd': '550ms' }} className="max-w-[520px] text-[19px] leading-relaxed">DriveFetch searches the sites live, cleans and de-duplicates the ads, and has AI agents read each one for risk and price, so you start with a shortlist instead of a hundred tabs.</p>
        </div>
      </section>

      {/* Pipeline */}
      <section className="px-5 sm:px-10 py-20 sm:py-24 flex flex-col gap-8">
        <h2 className="df-display text-[length:clamp(44px,5.5vw,84px)]"><SplitText text="What happens when you" /> <SplitText text="press search." className="text-df-red" start={4} /></h2>
        <ol data-stagger className="grid sm:grid-cols-2 lg:grid-cols-5 border-t-4 border-black dark:border-zinc-50">
          {STEPS.map((s, i) => (
            <li key={s.n} className="flex flex-col gap-2.5 py-6 pr-6 lg:mr-6 border-b lg:border-b-0 lg:border-r border-neutral-200 dark:border-zinc-800 last:border-r-0">
              <span className={`df-display text-[64px] ${i === 0 ? 'text-df-red' : ''}`}>{s.n}</span>
              <strong className="text-[21px] leading-tight">{s.t}</strong>
              <span className="text-[15px] leading-relaxed df-muted">{s.d}</span>
              <code className="mt-auto font-mono text-[11.5px] df-muted">{s.code}</code>
            </li>
          ))}
        </ol>
      </section>

      {/* Founder + FAQ */}
      <section className="bg-df-grey dark:bg-black border-y border-neutral-200 dark:border-zinc-800">
        <div className="px-5 sm:px-10 py-20 sm:py-24 grid gap-14 lg:gap-20 lg:grid-cols-2 items-start">
          <div className="flex flex-col gap-4">
            <span data-reveal="fade" className="df-label">BUILT BY</span>
            <div data-reveal="scale" className="flex flex-wrap bg-white text-black border-[5px] border-black max-w-[540px]">
              <img src={profilePic} alt="Muhammad Ismail" className="w-[150px] h-[190px] object-cover border-r-[5px] border-black" />
              <div className="flex-1 min-w-[220px] p-4 sm:p-5 flex flex-col gap-1.5">
                <span className="text-[10px] font-extrabold tracking-[0.2em]">ISLAMABAD · ICT</span>
                <strong className="df-display text-[34px]">Muhammad Ismail</strong>
                <span className="text-xs font-extrabold tracking-[0.08em] text-df-red-dark">LEAD ARCHITECT · AI ORCHESTRATOR</span>
                <span className="text-sm leading-relaxed">Engineering full-stack agentic systems and multi-agent architectures at FAST NUCES, Islamabad.</span>
                <div className="flex gap-4 mt-auto pt-2 text-sm font-bold">
                  <a href={REPO_URL} target="_blank" rel="noopener noreferrer" className="underline underline-offset-2 hover:text-df-red">GitHub</a>
                  <a href="https://muhammadismail.is-a.dev" target="_blank" rel="noopener noreferrer" className="underline underline-offset-2 hover:text-df-red">Portfolio</a>
                </div>
              </div>
            </div>
          </div>
          <div className="flex flex-col">
            <h2 className="df-display text-[length:clamp(40px,4.5vw,64px)] mb-4"><SplitText text="Questions" /></h2>
            {FAQS.map((f, i) => (
              <details key={f.q} open={i === 0} data-reveal style={{ '--rd': `${i * 70}ms` }} className="group border-t-2 border-black dark:border-zinc-50 last:border-b-2">
                <summary className="flex justify-between items-center gap-4 min-h-[64px] text-[18px] font-extrabold">
                  {f.q}
                  <span aria-hidden="true" className="text-3xl font-light text-df-red transition-transform group-open:rotate-45">+</span>
                </summary>
                <p className="mb-5 text-base leading-relaxed df-muted">{f.a}</p>
              </details>
            ))}
          </div>
        </div>
      </section>

      {/* Contact */}
      <section id="contact" className="px-5 sm:px-10 py-20 sm:py-24 flex flex-wrap gap-10 lg:gap-16 scroll-mt-20">
        <div className="flex-[1_1_380px] min-w-0 flex flex-col gap-4">
          <h2 className="df-display text-[length:clamp(48px,6vw,96px)]"><SplitText text="Say" /> <SplitText text="salaam." className="text-df-red" start={1} /></h2>
          <p data-reveal className="max-w-[420px] text-lg leading-relaxed df-muted">Found a bug, a wrong price or a site we should add? Send a note.</p>
        </div>
        <div className="flex-[1_1_520px] min-w-0">
          {isSubmitted ? (
            <div role="status" className="p-8 bg-df-red text-white flex flex-col gap-3 animate-df-fade-up">
              <strong className="df-display text-[44px]">Message sent.</strong>
              <span className="text-[17px]">Thanks, {name.trim().split(' ')[0] || 'friend'}. You’ll get a reply at {email.trim()}.</span>
              <button type="button" onClick={reset} className="self-start h-11 px-4 bg-black text-white text-sm font-extrabold">Send another</button>
            </div>
          ) : (
            <form onSubmit={handleSubmit} noValidate data-reveal className="flex flex-col gap-4">
              <div className="grid sm:grid-cols-2 gap-4">
                <div className="flex flex-col gap-1.5">
                  <label htmlFor="ab-name" className="text-sm font-extrabold">Name</label>
                  <input id="ab-name" name="name" type="text" maxLength={200} value={name} onChange={(e) => setName(e.target.value)} aria-invalid={nameBad} aria-describedby={nameBad ? 'ab-name-err' : undefined} className={`${fieldCls(nameBad)} h-[52px]`} />
                  {nameBad ? <span id="ab-name-err" className="text-[13px] font-bold text-df-red-dark dark:text-zinc-50">Add your name</span> : null}
                </div>
                <div className="flex flex-col gap-1.5">
                  <label htmlFor="ab-email" className="text-sm font-extrabold">Email</label>
                  <input id="ab-email" name="email" type="email" maxLength={200} value={email} onChange={(e) => setEmail(e.target.value)} aria-invalid={emailBad} aria-describedby={emailBad ? 'ab-email-err' : undefined} className={`${fieldCls(emailBad)} h-[52px]`} />
                  {emailBad ? <span id="ab-email-err" className="text-[13px] font-bold text-df-red-dark dark:text-zinc-50">That email doesn’t look right</span> : null}
                </div>
              </div>
              <div className="flex flex-col gap-1.5">
                <div className="flex justify-between">
                  <label htmlFor="ab-msg" className="text-sm font-extrabold">Message</label>
                  <span className="font-mono text-xs df-muted">{message.length}/200</span>
                </div>
                <textarea id="ab-msg" name="message" rows={5} maxLength={200} value={message} onChange={(e) => setMessage(e.target.value)} aria-invalid={msgBad} aria-describedby={msgBad ? 'ab-msg-err' : undefined} className={`${fieldCls(msgBad)} py-3 leading-relaxed resize-y`} />
                {msgBad ? <span id="ab-msg-err" className="text-[13px] font-bold text-df-red-dark dark:text-zinc-50">Write a short message</span> : null}
              </div>
              {submitError ? <div role="alert" className="p-4 border-2 border-df-red font-bold">{submitError}</div> : null}
              <button type="submit" disabled={isSubmitting} className="df-btn-red h-[60px] text-base tracking-[0.06em] gap-2.5">
                {isSubmitting ? <Spinner className="w-4 h-4" light /> : null}
                {isSubmitting ? 'SENDING…' : 'SEND MESSAGE'}
              </button>
            </form>
          )}
        </div>
      </section>
    </div>
  );
}

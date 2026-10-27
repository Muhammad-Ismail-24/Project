import { useState } from 'react';
import { Link } from 'react-router-dom';
import SEO from '../components/SEO';
import { privacySchema } from '../config/seoSchemas';

const SECTIONS = [
  {
    id: 'identity',
    t: 'Authentication & identity',
    short: 'Google signs you in; we never see a password.',
    body: 'DriveFetch uses Google OAuth 2.0 for secure, passwordless sign-in. When you sign in, we collect and store only your primary email address, full name and avatar image. We do not collect, process or store passwords at any point.',
  },
  {
    id: 'usage',
    t: 'Data usage & personalisation',
    short: 'Saved cars, your assistant’s name and chats, used only to help you.',
    body: 'To give you a continuous, personal matchmaking experience, we store your saved vehicles, AI assistant name preference and chat history. This data is used only to give the AI orchestrator the context of what you are looking for.',
  },
  {
    id: 'cookies',
    t: 'Cookies & local storage',
    short: 'One secure session cookie; a few preferences stay in your browser.',
    body: 'We keep you signed in with an encrypted, HttpOnly cookie. No tracking scripts are embedded. Cosmetic preferences such as light or dark mode, and your saved-car notes and buying stages, are kept in your browser’s local storage and never leave your device.',
  },
  {
    id: 'ai',
    t: 'Third-party AI & scraping',
    short: 'Your questions go to AI models; ads come from public sites.',
    body: 'DriveFetch is an autonomous aggregator. User queries are processed by external large language models to analyse vehicles in real time. Our engine reads public marketplace data, including PakWheels, OLX and Gari.pk, in real time. We do not claim ownership of, nor host original files for, any third-party listing.',
  },
  {
    id: 'law',
    t: 'Legal jurisdiction',
    short: 'Pakistani law, Islamabad Capital Territory.',
    body: 'This service operates under and is governed by the laws of Pakistan, under the jurisdiction of the Islamabad Capital Territory. Any legal disputes or compliance matters fall within this framework.',
  },
];

const STORE = [
  ['Name, email, avatar', 'Your account', 'DriveFetch database'],
  ['Saved vehicles', 'Your garage', 'DriveFetch database'],
  ['Assistant name and theme', 'Personalisation', 'DriveFetch database'],
  ['Chat history', 'Context for answers', 'DriveFetch database'],
  ['Session cookie', 'Keep you signed in', 'Your browser (HttpOnly)'],
  ['Theme, garage notes and stages', 'Preferences on this device', 'Your browser only'],
  ['Search and chat text', 'AI analysis', 'External AI providers'],
];

export default function PrivacyPolicy() {
  const [current, setCurrent] = useState(SECTIONS[0].id);
  const toc = [...SECTIONS.map((s) => ({ id: s.id, t: s.t })), { id: 'store', t: 'What we store' }, { id: 'requests', t: 'Questions or requests' }];

  return (
    <div className="w-full">
      {/* Indexed, not noindex: a public privacy policy is a trust signal. */}
      <SEO
        title="Privacy Policy"
        description="How DriveFetch collects, uses and protects your data, including Google OAuth authentication and saved vehicle preferences."
        path="/privacy"
        schema={privacySchema}
      />

      <section className="px-5 sm:px-10 pt-12 sm:pt-14 pb-10 flex flex-wrap justify-between items-end gap-6 border-b-2 border-black dark:border-zinc-50">
        <div className="flex flex-col gap-3.5">
          <span className="df-label">EFFECTIVE AUGUST 2026</span>
          <h1 className="df-display text-[length:clamp(60px,9vw,136px)]">Privacy <span className="text-df-red">policy.</span></h1>
        </div>
        <button type="button" onClick={() => window.print()} className="df-btn-outline h-12 px-5">Print</button>
      </section>

      <div className="flex flex-wrap">
        <nav aria-label="On this page" className="flex-[1_1_240px] min-w-0 lg:max-w-[320px] px-5 sm:px-10 py-8 sm:py-10 flex flex-col gap-0.5 lg:border-r border-neutral-200 dark:border-zinc-800 print:hidden">
          <span className="text-[13px] font-extrabold mb-2.5">On this page</span>
          {toc.map((c) => (
            <a
              key={c.id}
              href={`#${c.id}`}
              onClick={() => setCurrent(c.id)}
              aria-current={current === c.id ? 'true' : undefined}
              className={`min-h-[40px] flex items-center pl-3 border-l-4 text-[15px] ${current === c.id ? 'border-df-red font-extrabold' : 'border-transparent df-muted hover:text-black dark:hover:text-zinc-50'}`}
            >
              {c.t}
            </a>
          ))}
        </nav>

        <article className="flex-[999_1_560px] min-w-0 max-w-[920px] px-5 sm:px-10 py-8 sm:py-10 pb-24 flex flex-col gap-12">
          <div className="p-6 bg-black text-white flex flex-col gap-2.5">
            <strong className="text-[15px] tracking-[0.06em]">THE SHORT VERSION</strong>
            <span className="text-lg leading-relaxed">We use Google to sign you in, never see a password, keep only what makes your saved cars and chats work, and don’t run tracking scripts. Listings belong to the sites we link to.</span>
          </div>

          {SECTIONS.map((s, i) => (
            <section key={s.id} id={s.id} className="flex flex-col gap-3.5 scroll-mt-24">
              <h2 className="df-display text-[34px] leading-none"><span className="text-df-red">0{i + 1}</span> {s.t}</h2>
              <p className="pl-4 border-l-4 border-black dark:border-zinc-50 text-base font-bold leading-relaxed">In short: {s.short}</p>
              <p className="text-[17px] leading-[1.7] text-neutral-700 dark:text-zinc-300">{s.body}</p>
            </section>
          ))}

          <section id="store" className="flex flex-col gap-3.5 scroll-mt-24">
            <h2 className="df-display text-[34px] leading-none"><span className="text-df-red">06</span> What we store</h2>
            <div className="overflow-x-auto border-t-2 border-black dark:border-zinc-50">
              <table className="w-full min-w-[560px] border-collapse text-[15px] leading-snug">
                <thead>
                  <tr>
                    <th scope="col" className="text-left py-3 pr-3 text-[13px]">Data</th>
                    <th scope="col" className="text-left p-3 text-[13px]">Why</th>
                    <th scope="col" className="text-left p-3 text-[13px]">Where</th>
                  </tr>
                </thead>
                <tbody>
                  {STORE.map(([d, w, p]) => (
                    <tr key={d} className="border-t border-neutral-200 dark:border-zinc-800">
                      <th scope="row" className="text-left py-3 pr-3 font-extrabold">{d}</th>
                      <td className="p-3 text-neutral-700 dark:text-zinc-300">{w}</td>
                      <td className="p-3 text-neutral-700 dark:text-zinc-300">{p}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section id="requests" className="flex flex-col gap-3 scroll-mt-24">
            <h2 className="df-display text-[34px] leading-none"><span className="text-df-red">07</span> Questions or requests</h2>
            <p className="text-[17px] leading-[1.7] text-neutral-700 dark:text-zinc-300">
              To ask what we hold about you, or to have it deleted, use the <Link to="/about#contact" className="font-bold underline underline-offset-2 text-black dark:text-zinc-50">contact form</Link>. Signed-in users can remove saved cars and chats themselves at any time.
            </p>
          </section>
        </article>
      </div>
    </div>
  );
}

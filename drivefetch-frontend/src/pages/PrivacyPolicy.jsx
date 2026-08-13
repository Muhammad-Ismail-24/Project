import React from 'react';
import { Helmet } from 'react-helmet-async';

export default function PrivacyPolicy() {
  return (
    <main className="relative z-10 pt-28 md:pt-40 px-5 sm:px-8 lg:px-12 pb-20 md:pb-32 min-h-screen flex flex-col items-center selection:bg-df-black selection:text-df-white dark:selection:bg-white dark:selection:text-black">
      <Helmet>
        <title>Privacy Policy — DriveFetch</title>
        <meta name="description" content="Privacy Policy and Data Handling practices for DriveFetch." />
        <link rel="canonical" href="https://carfinderproject.vercel.app/privacy" />
      </Helmet>

      <div className="w-full max-w-4xl mx-auto space-y-16">
        
        {/* HEADER */}
        <div>
          <h1 className="text-5xl md:text-7xl font-black uppercase tracking-tighter text-df-black dark:text-zinc-50 leading-[0.9] mb-6">
            PRIVACY <span className="text-df-red">POLICY</span>
          </h1>
          <div className="font-mono text-sm sm:text-base font-bold text-df-black/60 dark:text-zinc-50/60 uppercase tracking-widest border-t-4 border-df-black dark:border-white pt-4">
            EFFECTIVE DATE: AUGUST 2026
          </div>
        </div>

        {/* CONTENT BLOCK */}
        <div className="bg-df-white dark:bg-black border-2 border-df-black dark:border-white shadow-[8px_8px_0px_#000000] dark:shadow-[8px_8px_0px_#ffffff] p-8 md:p-12 space-y-12">
          
          <section>
            <h2 className="text-2xl md:text-3xl font-black uppercase text-df-black dark:text-zinc-50 mb-4 tracking-tight">
              1. Authentication & Identity
            </h2>
            <p className="font-body text-base md:text-lg leading-relaxed text-df-black/80 dark:text-zinc-50/80">
              DriveFetch utilizes <strong>Google OAuth 2.0</strong> for secure and passwordless authentication. When you sign in, we collect and store only your primary email address, full name, and avatar image. We do <strong>not</strong> collect, process, or store passwords at any point.
            </p>
          </section>

          <div className="w-full h-px bg-df-black/20 dark:bg-white/20" />

          <section>
            <h2 className="text-2xl md:text-3xl font-black uppercase text-df-black dark:text-zinc-50 mb-4 tracking-tight">
              2. Data Usage & Personalization
            </h2>
            <p className="font-body text-base md:text-lg leading-relaxed text-df-black/80 dark:text-zinc-50/80">
              To provide a continuous and personalized matchmaking experience, our systems securely store your saved vehicles, AI assistant name preferences, and historical chat transcripts. This data is strictly used to inform the AI orchestrator of your specific market needs and context.
            </p>
          </section>

          <div className="w-full h-px bg-df-black/20 dark:bg-white/20" />

          <section>
            <h2 className="text-2xl md:text-3xl font-black uppercase text-df-black dark:text-zinc-50 mb-4 tracking-tight">
              3. Cookies & Local Storage
            </h2>
            <p className="font-body text-base md:text-lg leading-relaxed text-df-black/80 dark:text-zinc-50/80">
              We deploy strict security measures for session management by utilizing encrypted, <strong>HttpOnly cookies</strong> to maintain your authenticated state. No tracking scripts are embedded. For purely cosmetic UI preferences (such as the Light/Dark Mode toggle), we utilize local browser storage (<code>localStorage</code>).
            </p>
          </section>

          <div className="w-full h-px bg-df-black/20 dark:bg-white/20" />

          <section>
            <h2 className="text-2xl md:text-3xl font-black uppercase text-df-black dark:text-zinc-50 mb-4 tracking-tight">
              4. Third-Party AI & Scraping
            </h2>
            <p className="font-body text-base md:text-lg leading-relaxed text-df-black/80 dark:text-zinc-50/80">
              DriveFetch is an autonomous aggregator. User queries are processed through external large language models (LLMs) to provide real-time vehicle analysis. Our engine scrapes public marketplace data—including PakWheels, OLX, and Gari.pk—in real-time. We do not claim ownership of, nor host original files for, any third-party listings.
            </p>
          </section>

          <div className="w-full h-px bg-df-black/20 dark:bg-white/20" />

          <section>
            <h2 className="text-2xl md:text-3xl font-black uppercase text-df-black dark:text-zinc-50 mb-4 tracking-tight">
              5. Legal Jurisdiction
            </h2>
            <p className="font-body text-base md:text-lg leading-relaxed text-df-black/80 dark:text-zinc-50/80">
              This service operates under and is governed by the laws of Pakistan, specifically under the jurisdiction of the Islamabad Capital Territory. Any legal disputes or compliance matters fall strictly within this governing framework.
            </p>
          </section>

        </div>

      </div>
    </main>
  );
}

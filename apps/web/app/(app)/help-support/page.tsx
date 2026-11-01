import {
  LifeBuoy,
  MessageCircle,
  Users,
  ShieldCheck,
  Bug,
  Mail,
  ArrowUpRight,
  Lightbulb,
  HelpCircle,
} from "lucide-react";

const supportEmail = process.env.NEXT_PUBLIC_SUPPORT_EMAIL;

const supportOptions = [
  {
    icon: MessageCircle,
    title: "Gameplay & Mysteries",
    description:
      "Having trouble understanding a mystery, sharing clues, or solving a challenge?",
    subject: "Pairza Gameplay Support",
  },
  {
    icon: Users,
    title: "Matchmaking & Friends",
    description:
      "Experiencing matchmaking issues or having trouble connecting with another player?",
    subject: "Pairza Matchmaking Support",
  },
  {
    icon: ShieldCheck,
    title: "Account & Security",
    description:
      "Need help with your account, login, privacy, or a security concern?",
    subject: "Pairza Account & Security",
  },
  {
    icon: Bug,
    title: "Report a Problem",
    description:
      "Found a bug or something that isn't working as expected? Let us know.",
    subject: "Pairza Bug Report",
  },
];

function emailLink(subject: string) {
  return `mailto:${supportEmail}?subject=${encodeURIComponent(subject)}`;
}

export default function HelpSupportPage() {
  return (
    <div className="mx-auto max-w-5xl space-y-10">
      {/* Header */}
      <section className="space-y-3">
        <div className="flex items-center gap-2 text-sm font-medium text-signal-teal">
          <LifeBuoy className="h-4 w-4" />
          Pairza Support
        </div>

        <h1 className="font-display text-3xl font-bold tracking-tight text-ink sm:text-4xl">
          How can we help you?
        </h1>

        <p className="max-w-2xl text-sm leading-7 text-ink-muted sm:text-base">
          Whether you're solving a mystery, connecting with another player,
          or exploring Pairza, we're here to help make your experience better.
        </p>
      </section>

      {/* Main contact card */}
      <section className="relative overflow-hidden rounded-2xl border border-signal-teal/20 bg-void-elevated p-6 sm:p-8">
        <div className="pointer-events-none absolute -right-16 -top-20 h-56 w-56 rounded-full bg-signal-teal/10 blur-3xl" />

        <div className="relative flex flex-col gap-6 sm:flex-row sm:items-center sm:justify-between">
          <div className="max-w-xl space-y-3">
            <span className="inline-flex items-center gap-2 rounded-full border border-signal-teal/20 bg-signal-teal/10 px-3 py-1 text-xs font-semibold text-signal-teal">
              <Mail className="h-3.5 w-3.5" />
              Get in touch
            </span>

            <h2 className="font-display text-2xl font-bold text-ink">
              Talk to the Pairza team
            </h2>

            <p className="text-sm leading-6 text-ink-muted">
              Send us your questions, feedback, or concerns. We value every
              message and every suggestion from our players.
            </p>

            <p className="break-all text-sm font-semibold text-signal-teal">
              {supportEmail}
            </p>
          </div>

          <a
            href={emailLink("Pairza Support")}
            className="inline-flex shrink-0 items-center justify-center gap-2 rounded-xl bg-signal-teal px-5 py-3 text-sm font-bold text-void transition hover:brightness-110"
          >
            Contact support
            <ArrowUpRight className="h-4 w-4" />
          </a>
        </div>
      </section>

      {/* Support categories */}
      <section className="space-y-5">
        <div className="space-y-2">
          <h2 className="font-display text-xl font-bold text-ink">
            What do you need help with?
          </h2>
          <p className="text-sm text-ink-muted">
            Choose a topic to send us an email with a relevant subject.
          </p>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          {supportOptions.map((option) => {
            const Icon = option.icon;

            return (
              <a
                key={option.title}
                href={emailLink(option.subject)}
                className="group rounded-2xl border border-white/[0.08] bg-void-elevated p-5 transition hover:border-signal-teal/30 hover:bg-void-elevated-2"
              >
                <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-xl border border-signal-teal/15 bg-signal-teal/10 text-signal-teal">
                  <Icon className="h-5 w-5" />
                </div>

                <div className="mb-2 flex items-center justify-between gap-3">
                  <h3 className="font-semibold text-ink">
                    {option.title}
                  </h3>
                  <ArrowUpRight className="h-4 w-4 shrink-0 text-ink-faint transition group-hover:text-signal-teal" />
                </div>

                <p className="text-sm leading-6 text-ink-muted">
                  {option.description}
                </p>
              </a>
            );
          })}
        </div>
      </section>

      {/* Product updates */}
      <section className="rounded-2xl border border-white/[0.08] bg-void-elevated p-6 sm:p-7">
        <div className="flex items-start gap-4">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-white/5 text-signal-teal">
            <Lightbulb className="h-5 w-5" />
          </div>

          <div className="min-w-0 flex-1 space-y-2">
            <h2 className="font-display text-lg font-bold text-ink">
              Product updates & suggestions
            </h2>
            <p className="text-sm leading-6 text-ink-muted">
              Curious about upcoming features? Have an idea that could make
              Pairza better? We'd love to hear from you.
            </p>

            <a
              href={emailLink("Pairza Product Updates & Suggestions")}
              className="inline-flex items-center gap-2 pt-2 text-sm font-semibold text-signal-teal hover:underline"
            >
              Contact us about updates
              <ArrowUpRight className="h-4 w-4" />
            </a>
          </div>
        </div>
      </section>

      {/* Closing note */}
      <section className="flex items-start gap-3 border-t border-white/[0.08] pt-6">
        <HelpCircle className="mt-0.5 h-5 w-5 shrink-0 text-ink-faint" />
        <p className="text-xs leading-6 text-ink-faint">
          When contacting support, please include a description of the issue
          and relevant screenshots if possible. For account-related concerns,
          never share your password or verification codes.
        </p>
      </section>
    </div>
  );
}

import { EnvelopeIcon } from "@heroicons/react/24/outline";
import InboundMailPanel from "@/components/InboundMailPanel";

export default function InboundMail() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-bold text-slate-900">
          <EnvelopeIcon className="h-8 w-8 text-brand-600" />
          入站邮件
        </h1>
      </div>
      <InboundMailPanel />
    </div>
  );
}

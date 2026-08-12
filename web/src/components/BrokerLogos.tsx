export type BrokerKey =
  | "tiger"
  | "longbridge"
  | "ibkr"
  | "ibkr_web"
  | "futu"
  | "schwab"
  | "alpaca"
  | "usmart";

const IMAGE_LOGOS: Record<BrokerKey, { src: string; alt: string; className: string; surface: string }> = {
  tiger: {
    src: "/brokers/tiger.png",
    alt: "Tiger Brokers",
    className: "h-7 w-7 rounded-md object-contain",
    surface: "bg-[#ffe000]",
  },
  longbridge: {
    src: "/brokers/longbridge-mark.svg",
    alt: "Longbridge",
    className: "h-7 w-7 object-contain",
    surface: "bg-white",
  },
  ibkr: {
    src: "/brokers/ibkr-mark-v2.svg",
    alt: "Interactive Brokers",
    className: "h-7 w-7 object-contain",
    surface: "bg-white",
  },
  ibkr_web: {
    src: "/brokers/ibkr-mark-v2.svg",
    alt: "Interactive Brokers Web API",
    className: "h-7 w-7 object-contain",
    surface: "bg-white",
  },
  futu: {
    src: "/brokers/futubull-mark-v2.png",
    alt: "Futu",
    className: "h-8 w-8 object-contain",
    surface: "bg-white",
  },
  schwab: {
    src: "/brokers/schwab.svg",
    alt: "Charles Schwab",
    className: "h-7 w-7 rounded-md object-contain",
    surface: "bg-[#00a0df]",
  },
  alpaca: {
    src: "/brokers/alpaca.png",
    alt: "Alpaca",
    className: "h-7 w-7 rounded-md object-contain",
    surface: "bg-white",
  },
  usmart: {
    src: "/brokers/usmart.png",
    alt: "uSMART",
    className: "h-7 w-7 rounded-md object-contain",
    surface: "bg-[#0B3D91]",
  },
};

type BrokerLogoProps = {
  broker: BrokerKey;
  className?: string;
  framed?: boolean;
};

export function BrokerLogo({ broker, className, framed = false }: BrokerLogoProps) {
  const logo = IMAGE_LOGOS[broker];
  if (!logo) return null;
  const image = (
    <img
      src={logo.src}
      alt={logo.alt}
      className={className ?? logo.className}
      loading="lazy"
      decoding="async"
    />
  );
  if (!framed) return image;
  return (
    <span className={`flex h-11 min-w-11 items-center justify-center rounded-xl border border-slate-200 px-2 shadow-sm ${logo.surface}`}>
      {image}
    </span>
  );
}

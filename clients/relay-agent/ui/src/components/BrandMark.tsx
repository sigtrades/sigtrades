const LOGO_SRC = `${import.meta.env.BASE_URL}logo.png`;

type Props = {
  subtitle?: string;
  compact?: boolean;
};

export default function BrandMark({ subtitle, compact = false }: Props) {
  return (
    <div className={`logo${compact ? " logo-compact" : ""}`}>
      <img src={LOGO_SRC} alt="" className="logo-image" />
      <span>{subtitle ? subtitle : "sigtrades agent"}</span>
    </div>
  );
}

export { LOGO_SRC };

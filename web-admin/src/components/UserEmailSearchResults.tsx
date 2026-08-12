import type { UserSearchHit } from "@/hooks/useDebouncedUserSearch";

type Props = {
  query: string;
  hits: UserSearchHit[];
  searching: boolean;
  searched: boolean;
  error: string | null;
  canSearch: boolean;
  minQueryLen: number;
  excludeIds?: Set<string>;
  onSelect: (user: UserSearchHit) => void;
};

export default function UserEmailSearchResults({
  query,
  hits,
  searching,
  searched,
  error,
  canSearch,
  minQueryLen,
  excludeIds,
  onSelect,
}: Props) {
  if (!canSearch) {
    if (query.trim().length > 0 && query.trim().length < minQueryLen) {
      return <p className="mt-2 text-xs text-slate-400">至少输入 {minQueryLen} 个字符</p>;
    }
    return null;
  }

  const visible = hits.filter((u) => !excludeIds?.has(u.id));

  return (
    <div className="mt-2 rounded-lg border border-slate-200 bg-white">
      {searching ? (
        <p className="px-3 py-2 text-xs text-slate-400">搜索中…</p>
      ) : error ? (
        <p className="px-3 py-2 text-xs text-red-600">{error}</p>
      ) : searched && visible.length === 0 ? (
        <p className="px-3 py-2 text-xs text-slate-500">未找到匹配「{query.trim()}」的用户</p>
      ) : (
        <ul className="max-h-32 overflow-y-auto">
          {visible.map((u) => (
            <li key={u.id} className="border-b border-slate-100 last:border-b-0">
              <button
                type="button"
                className="block w-full px-3 py-2 text-left text-sm hover:bg-slate-50"
                onClick={() => onSelect(u)}
              >
                <span className="font-medium text-slate-900">{u.email}</span>
                {u.display_name ? <span className="ml-2 text-xs text-slate-400">{u.display_name}</span> : null}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

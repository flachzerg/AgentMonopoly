import type { FC } from "react";

type AgentStreamEntry = {
  ts: string;
  modelTag: string;
  action: string;
  status: "ok" | "fallback";
  summary: string;
};

type Props = {
  entries: AgentStreamEntry[];
};

export const AgentStreamPanel: FC<Props> = ({ entries }) => {
  const latest = [...entries].slice(-30).reverse();

  return (
    <section className="panel stream-panel">
      <h2>Agent 输出流</h2>
      {latest.length === 0 ? (
        <p className="muted">暂无 Agent 输出。</p>
      ) : (
        <div className="stream-list">
          {latest.map((item, index) => (
            <article key={`${item.ts}-${index}`} className="stream-item">
              <header>
                <span>{item.modelTag}</span>
                <span className={item.status === "fallback" ? "stream-fallback" : "stream-ok"}>{item.status}</span>
              </header>
              <div className="stream-action">action: {item.action}</div>
              <p>{item.summary || "(无摘要)"}</p>
            </article>
          ))}
        </div>
      )}
    </section>
  );
};

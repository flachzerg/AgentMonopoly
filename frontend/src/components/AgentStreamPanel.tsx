import type { FC } from "react";

type AgentStreamEntry = {
  id: string;
  ts: string;
  playerId: string;
  playerName: string;
  avatar: string;
  thought: string;
  modelTag: string;
  action: string;
  status: "streaming" | "ok" | "fallback";
};

type Props = {
  entries: AgentStreamEntry[];
};

export const AgentStreamPanel: FC<Props> = ({ entries }) => {
  const latest = [...entries].slice(-40);

  return (
    <section className="panel stream-panel">
      <h2>Agent 思维群聊</h2>
      {latest.length === 0 ? (
        <p className="muted">暂无 Agent 思考输出。</p>
      ) : (
        <div className="stream-list">
          {latest.map((item) => (
            <article key={item.id} className="chat-row">
              <div className="chat-avatar" title={item.playerId}>
                {item.avatar}
              </div>
              <div className="chat-body">
                <header className="chat-meta">
                  <span className="chat-name">{item.playerName}</span>
                  <span className={item.status === "fallback" ? "stream-fallback" : item.status === "streaming" ? "stream-streaming" : "stream-ok"}>
                    {item.status}
                  </span>
                </header>
                <div className="chat-bubble">
                  <p>{item.thought || "..."}</p>
                  {item.status === "streaming" ? <span className="typing-dot">...</span> : null}
                </div>
                <div className="stream-action">
                  {item.action ? `-> ${item.action}` : ""}
                  {item.modelTag ? ` (${item.modelTag})` : ""}
                </div>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
};

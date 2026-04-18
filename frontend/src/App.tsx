import { create } from "zustand";

type GameState = {
  roomId: string;
  currentRound: number;
  logs: string[];
  setRoomId: (roomId: string) => void;
  addLog: (line: string) => void;
};

const useGameStore = create<GameState>((set) => ({
  roomId: "demo-room",
  currentRound: 1,
  logs: ["系统启动：等待创建房间"],
  setRoomId: (roomId) => set({ roomId }),
  addLog: (line) => set((s) => ({ logs: [...s.logs, line] })),
}));

export default function App() {
  const { roomId, currentRound, logs, addLog } = useGameStore();

  return (
    <div className="page">
      <header>
        <h1>AgentMonopoly MVP</h1>
        <p>前后端分离 | React + FastAPI + PydanticAI</p>
      </header>
      <section className="panel-row">
        <div className="panel">
          <h2>对局信息</h2>
          <p>房间号: {roomId}</p>
          <p>当前回合: {currentRound}</p>
          <button onClick={() => addLog("前端操作：请求掷骰子（示例）")}>模拟操作</button>
        </div>
        <div className="panel">
          <h2>日志流</h2>
          <ul>
            {logs.map((line, idx) => (
              <li key={`${idx}-${line}`}>{line}</li>
            ))}
          </ul>
        </div>
      </section>
    </div>
  );
}

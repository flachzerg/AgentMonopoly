import { Navigate, Route, BrowserRouter as Router, Routes } from "react-router-dom";

import { AppShell } from "./components/AppShell";
import GamePage from "./pages/GamePage";
import ReplayPage from "./pages/ReplayPage";
import SetupPage from "./pages/SetupPage";

export default function App() {
  return (
    <Router>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/" element={<Navigate to="/setup" replace />} />
          <Route path="/setup" element={<SetupPage />} />
          <Route path="/game/:gameId" element={<GamePage />} />
          <Route path="/replay/:gameId" element={<ReplayPage />} />
          <Route path="*" element={<Navigate to="/setup" replace />} />
        </Route>
      </Routes>
    </Router>
  );
}

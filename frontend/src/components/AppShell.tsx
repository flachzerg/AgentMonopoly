import { NavLink, Outlet, useLocation, useMatch } from "react-router-dom";

import { useGameStore } from "../store/gameStore";

function buildLinkClass({ isActive }: { isActive: boolean }) {
  return isActive ? "site-nav__link site-nav__link--active" : "site-nav__link";
}

export function AppShell() {
  const location = useLocation();
  const gameMatch = useMatch("/game/:gameId");
  const replayMatch = useMatch("/replay/:gameId");
  const latestGameId = useGameStore((state) => state.gameId);

  const activeGameId = gameMatch?.params.gameId ?? replayMatch?.params.gameId ?? latestGameId;
  const isMatchExperience = location.pathname.startsWith("/game/");

  return (
    <div className="site-shell">
      <header className={isMatchExperience ? "site-header site-header--immersive" : "site-header"}>
        <div className="site-header__inner">
          <div className={isMatchExperience ? "site-brand site-brand--compact" : "site-brand"}>
            <span className="site-brand__kicker">Agent Monopoly</span>
            <span className="site-brand__name">实时博弈控制台</span>
          </div>

          <nav className={isMatchExperience ? "site-nav site-nav--immersive" : "site-nav"} aria-label="主导航">
            <NavLink to="/setup" className={buildLinkClass}>
              配置页
            </NavLink>
            {activeGameId ? (
              <NavLink to={`/game/${encodeURIComponent(activeGameId)}`} className={buildLinkClass}>
                对局页
              </NavLink>
            ) : null}
            {activeGameId ? (
              <NavLink to={`/replay/${encodeURIComponent(activeGameId)}`} className={buildLinkClass}>
                复盘页
              </NavLink>
            ) : null}
          </nav>
        </div>
      </header>

      <main className={isMatchExperience ? "site-main site-main--immersive" : "site-main"}>
        <Outlet />
      </main>

      {isMatchExperience ? null : (
        <footer className="site-footer">
          <div className="site-footer__inner">
            <p>配置、对局、复盘 一体化流程</p>
            <p className="site-footer__muted">Setup → Game → Replay</p>
          </div>
        </footer>
      )}
    </div>
  );
}

import { NavLink, Route, Routes } from "react-router-dom";

import { useStatus } from "./api/hooks";
import StatusPill from "./components/StatusPill";
import { useAttentionNotifications, useTabBadge } from "./components/useNotifications";
import InboxPage from "./pages/InboxPage";
import SettingsPage from "./pages/SettingsPage";
import WatchesPage from "./pages/WatchesPage";

export default function App() {
  const { data: status } = useStatus();
  const unseen = status?.attention_unseen ?? 0;
  useAttentionNotifications();
  useTabBadge(unseen);

  return (
    <div className="app-shell">
      <header className="app-header">
        <NavLink to="/" className="brand" end>
          discord_watch
        </NavLink>
        <nav className="nav-links">
          <NavLink to="/" end>
            Inbox{unseen > 0 && <span className="count-badge">{unseen}</span>}
          </NavLink>
          <NavLink to="/watches">Watching</NavLink>
          <NavLink to="/settings">Settings</NavLink>
          <StatusPill status={status} />
        </nav>
      </header>
      <main className="app-main">
        <Routes>
          <Route path="/" element={<InboxPage />} />
          <Route path="/watches" element={<WatchesPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
      </main>
    </div>
  );
}

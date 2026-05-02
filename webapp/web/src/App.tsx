import { Routes, Route } from "react-router-dom";
import { AppShell } from "./components/layout/AppShell";
import { Dashboard } from "./pages/Dashboard";
import { Channels } from "./pages/Channels";
import { ChannelDetail } from "./pages/ChannelDetail";
import { TwitterPage } from "./pages/TwitterPage";
import { Series } from "./pages/Series";
import { Settings } from "./pages/Settings";
import { Generate } from "./pages/Generate";
import { Storage } from "./pages/Storage";
import { Affiliate } from "./pages/Affiliate";
import { Outreach } from "./pages/Outreach";
import { NotFound } from "./pages/NotFound";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<AppShell />}>
        <Route index element={<Dashboard />} />
        <Route path="generate" element={<Generate />} />
        <Route path="channels" element={<Channels />} />
        <Route path="channels/:id" element={<ChannelDetail />} />
        <Route path="twitter" element={<TwitterPage />} />
        <Route path="series" element={<Series />} />
        <Route path="settings" element={<Settings />} />
        <Route path="storage" element={<Storage />} />
        <Route path="affiliate" element={<Affiliate />} />
        <Route path="outreach" element={<Outreach />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}

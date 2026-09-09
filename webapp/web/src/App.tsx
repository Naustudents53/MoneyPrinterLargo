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
import { Thumbnails } from "./pages/Thumbnails";
import { PhotoPrompts } from "./pages/PhotoPrompts";
import { Affiliate } from "./pages/Affiliate";
import { Outreach } from "./pages/Outreach";
import { Operations } from "./pages/Operations";
import { NotFound } from "./pages/NotFound";
import { HiggsfieldStudio } from "./pages/HiggsfieldStudio";
import { HiggsfieldNew } from "./pages/HiggsfieldNew";
import { HiggsfieldProject } from "./pages/HiggsfieldProject";

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
        <Route path="thumbnails" element={<Thumbnails />} />
        <Route path="photo-prompts" element={<PhotoPrompts />} />
        <Route path="affiliate" element={<Affiliate />} />
        <Route path="outreach" element={<Outreach />} />
        <Route path="operations" element={<Operations />} />
        <Route path="higgsfield" element={<HiggsfieldStudio />} />
        <Route path="higgsfield/new" element={<HiggsfieldNew />} />
        <Route path="higgsfield/:id" element={<HiggsfieldProject />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}

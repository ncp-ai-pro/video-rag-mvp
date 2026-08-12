import { Navigate, Route, Routes } from "react-router-dom";

import GlobalLayout from "./components/layout/global-layout";
import IndexPage from "./pages/IndexPage";
import WorkspacePage from "./pages/WorkspacePage";

export default function RootRouter() {
  return (
    <Routes>
      <Route element={<GlobalLayout />}>
        <Route path="/" element={<IndexPage />} />
        <Route path="/workspace" element={<WorkspacePage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}

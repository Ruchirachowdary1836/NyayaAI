import { Navigate, Route, Routes } from 'react-router-dom';
import { Shell } from './components/Shell';
import { SearchWorkspace } from './features/SearchWorkspace';
import {
  AdminPage,
  ComparePage,
  DocumentLibraryPage,
  DocumentPage,
  ExperimentsPage,
  RoadmapPage,
} from './features/ResearchPages';

export default function App() {
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<SearchWorkspace />} />
        <Route path="compare" element={<ComparePage />} />
        <Route path="experiments" element={<ExperimentsPage />} />
        <Route path="documents" element={<DocumentLibraryPage />} />
        <Route path="documents/:documentId" element={<DocumentPage />} />
        <Route path="admin" element={<AdminPage />} />
        <Route path="roadmap" element={<RoadmapPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}

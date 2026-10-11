import { Navigate, Route, Routes } from 'react-router-dom';
import { PublicLayout } from './components/PublicLayout';
import { AnonymousOnly, RequireAdmin, RequireAuth } from './components/RouteGuards';
import { Shell } from './components/Shell';
import { AdminPage, ProfilePage, RoadmapPage } from './features/AccountPages';
import { LoginPage, RegisterPage } from './features/AuthPages';
import { ComparePage } from './features/ComparePage';
import { DocumentLibraryPage, DocumentPage } from './features/CorpusPages';
import { DashboardPage } from './features/DashboardPage';
import { ExperimentDetailPage, ExperimentsPage } from './features/ExperimentsPage';
import { LandingPage } from './features/LandingPage';
import { MyDocumentPage, MyDocumentsPage } from './features/LibraryPages';
import { NotFoundPage } from './features/NotFoundPage';
import { SearchWorkspace } from './features/SearchWorkspace';

export default function App() {
  return (
    <Routes>
      <Route element={<PublicLayout />}>
        <Route index element={<LandingPage />} />
        <Route element={<AnonymousOnly />}>
          <Route path="login" element={<LoginPage />} />
          <Route path="register" element={<RegisterPage />} />
        </Route>
        <Route path="*" element={<NotFoundPage />} />
      </Route>
      <Route element={<RequireAuth />}>
        <Route element={<Shell />}>
          <Route path="dashboard" element={<DashboardPage />} />
          <Route path="search" element={<SearchWorkspace />} />
          <Route path="compare" element={<ComparePage />} />
          <Route path="experiments" element={<ExperimentsPage />} />
          <Route path="experiments/:experimentId" element={<ExperimentDetailPage />} />
          <Route path="documents" element={<DocumentLibraryPage />} />
          <Route path="documents/:documentId" element={<DocumentPage />} />
          <Route path="library" element={<MyDocumentsPage />} />
          <Route path="library/:documentId" element={<MyDocumentPage />} />
          <Route path="profile" element={<ProfilePage />} />
          <Route path="roadmap" element={<RoadmapPage />} />
          <Route element={<RequireAdmin />}>
            <Route path="admin" element={<AdminPage />} />
          </Route>
          <Route path="workspace" element={<Navigate to="/search" replace />} />
        </Route>
      </Route>
    </Routes>
  );
}

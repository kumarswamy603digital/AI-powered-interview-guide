import { Navigate, Route, Routes } from "react-router-dom";
import { LoginPage } from "./pages/LoginPage";
import { SignupPage } from "./pages/SignupPage";
import { DashboardPage } from "./pages/DashboardPage";
import { DecisionDashboardPage } from "./pages/DecisionDashboardPage";
import { HrDashboardPage } from "./pages/HrDashboardPage";
import { PipelinePage } from "./pages/PipelinePage";
import { PeoplePage } from "./pages/PeoplePage";
import { EmployeeProfilePage } from "./pages/EmployeeProfilePage";
import { AttritionPage } from "./pages/AttritionPage";
import { PerformancePage } from "./pages/PerformancePage";
import { SkillGraphPage } from "./pages/SkillGraphPage";
import { OnboardingPage } from "./pages/OnboardingPage";
import { PolicyPage } from "./pages/PolicyPage";
import { InterviewPage } from "./pages/InterviewPage";
import { ProtectedRoute } from "./components/ProtectedRoute";

/** Every HR route is protected; `/hr` is the decision dashboard landing page. */
const PROTECTED_ROUTES: { path: string; element: JSX.Element }[] = [
  { path: "/dashboard", element: <DashboardPage /> },
  { path: "/hr", element: <DecisionDashboardPage /> },
  { path: "/recruitment", element: <HrDashboardPage /> },
  { path: "/pipeline", element: <PipelinePage /> },
  { path: "/people", element: <PeoplePage /> },
  { path: "/people/:employeeId", element: <EmployeeProfilePage /> },
  { path: "/attrition", element: <AttritionPage /> },
  { path: "/performance", element: <PerformancePage /> },
  { path: "/skills", element: <SkillGraphPage /> },
  { path: "/onboarding", element: <OnboardingPage /> },
  { path: "/policies", element: <PolicyPage /> },
  { path: "/interview", element: <InterviewPage /> }
];

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/signup" element={<SignupPage />} />

      {PROTECTED_ROUTES.map(({ path, element }) => (
        <Route key={path} path={path} element={<ProtectedRoute>{element}</ProtectedRoute>} />
      ))}

      <Route path="*" element={<Navigate to="/hr" replace />} />
    </Routes>
  );
}

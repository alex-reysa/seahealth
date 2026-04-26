/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { Layout } from './components/Layout';
import { Dashboard } from './pages/Dashboard';
import { PlannerQuery } from './pages/PlannerQuery';
import { FacilityAudit } from './pages/FacilityAudit';

function NotFound() {
  return (
    <div className="flex h-full items-center justify-center bg-surface-canvas p-8">
      <div className="max-w-md rounded-xl border border-border-subtle bg-white p-8 text-center shadow-elevation-2">
        <h1 className="text-heading-l mb-2">Route unavailable</h1>
        <p className="text-body text-content-secondary">
          This demo only includes Map Workbench, Planner Query, and Facility Audit.
        </p>
      </div>
    </div>
  );
}

function DesertMapAlias() {
  const location = useLocation();
  return <Navigate to={`/${location.search}`} replace />;
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="desert-map" element={<DesertMapAlias />} />
          <Route path="planner-query" element={<PlannerQuery />} />
          <Route path="facilities/:facility_id" element={<FacilityAudit />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

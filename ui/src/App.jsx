import React from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import AppNavbar from "./components/AppNavbar.jsx";
import OverviewPage from "./pages/OverviewPage.jsx";
import ProjectPage from "./pages/ProjectPage.jsx";
import TryItPage from "./pages/TryItPage.jsx";

function App() {
    return (
        <div className="page-wrap">
            <AppNavbar />
            <Routes>
                <Route path="/" element={<OverviewPage />} />
                <Route path="/project" element={<ProjectPage />} />
                <Route path="/try-it" element={<TryItPage />} />
                <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
        </div>
    );
}

export default App;

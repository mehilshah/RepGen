import React from "react";
import { NavLink } from "react-router-dom";
import { Activity, FlaskConical } from "lucide-react";

const NAV_ITEMS = [
    { to: "/", label: "Overview" },
    { to: "/project", label: "Project" },
    { to: "/try-it", label: "Try-It" },
];

function AppNavbar() {
    return (
        <header className="app-nav-wrap">
            <div className="app-nav">
                <NavLink to="/" className="brand-pill" aria-label="RepGen Home">
                    <Activity size={18} />
                    <span className="brand-mark">RepGen</span>
                </NavLink>

                <nav className="nav-tabs" aria-label="Primary">
                    {NAV_ITEMS.map((item) => (
                        <NavLink
                            key={item.to}
                            to={item.to}
                            end={item.to === "/"}
                            className={({ isActive }) => `nav-tab ${isActive ? "nav-tab-active" : ""}`}
                        >
                            {item.label}
                        </NavLink>
                    ))}
                </nav>

                <NavLink to="/try-it" className="nav-cta">
                    <FlaskConical size={16} />
                    <span>Launch Workspace</span>
                </NavLink>
            </div>
        </header>
    );
}

export default AppNavbar;

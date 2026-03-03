import React from "react";
import { NavLink } from "react-router-dom";
import { FlaskConical } from "lucide-react";

const NAV_ITEMS = [
    { to: "/", label: "Overview" },
    { to: "/project", label: "Project" }
];

function AppNavbar() {
    return (
        <header className="app-nav-wrap">
            <div className="app-nav">
                <NavLink to="/" aria-label="RepGen Home" className="brand-home">
                    <span className="brand-dot" />
                    <span className="brand-stack">
                        <span className="brand-mark">RepGen</span>
                        <span className="brand-tagline">DL Bug Reproduction</span>
                    </span>
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

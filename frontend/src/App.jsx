import React, { useEffect, useState } from "react";
import { api, clearSession, getStoredUser, getToken } from "./api.js";
import LoginPage from "./pages/LoginPage.jsx";
import EmployeeHome from "./pages/EmployeeHome.jsx";
import AdminPage from "./pages/AdminPage.jsx";

function currentRoute() {
  const hash = window.location.hash.replace(/^#/, "") || "/";
  return hash.startsWith("/") ? hash : `/${hash}`;
}

export default function App() {
  const [user, setUser] = useState(() => (getToken() ? getStoredUser() : null));
  const [route, setRoute] = useState(currentRoute);

  useEffect(() => {
    const onHash = () => setRoute(currentRoute());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  useEffect(() => {
    if (!getToken()) return;
    api
      .me()
      .then((me) => setUser(me))
      .catch(() => {
        clearSession();
        setUser(null);
        window.location.hash = "#/login";
      });
  }, []);

  useEffect(() => {
    if (!user) {
      if (route !== "/login") window.location.hash = "#/login";
      return;
    }
    if (route === "/login") {
      window.location.hash = user.role === "admin" ? "#/admin" : "#/";
      return;
    }
    if (route === "/admin" && user.role !== "admin") {
      window.location.hash = "#/";
    }
  }, [user, route]);

  function handleLogin(nextUser) {
    setUser(nextUser);
    window.location.hash = nextUser.role === "admin" ? "#/admin" : "#/";
  }

  function handleLogout() {
    setUser(null);
    window.location.hash = "#/login";
  }

  if (!user) {
    return <LoginPage onLoggedIn={handleLogin} />;
  }

  if (route === "/admin" && user.role === "admin") {
    return <AdminPage user={user} onLogout={handleLogout} />;
  }

  return <EmployeeHome user={user} onLogout={handleLogout} />;
}

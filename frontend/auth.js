let isLogin = true;
let currentLang = "en";

// ── Translations ──────────────────────────────────────────────────────────────
const translations = {
  en: {
    loginTitle: "Login",
    firstName: "First Name",
    lastName: "Last Name",
    email: "Email",
    password: "Password",
    signIn: "Sign In",
    dontHaveAccount: "Don't have an account?",
    register: "Register",
    alreadyHaveAccount: "Already have an account?",
    createAccount: "Create Account",
    login: "Login",
  },
  lt: {
    loginTitle: "Prisijungimas",
    firstName: "Vardas",
    lastName: "Pavardė",
    email: "El. paštas",
    password: "Slaptažodis",
    signIn: "Prisijungti",
    dontHaveAccount: "Neturite paskyros?",
    register: "Registruotis",
    alreadyHaveAccount: "Jau turite paskyrą?",
    createAccount: "Sukurti paskyrą",
    login: "Prisijungti",
  },
};

function t(key) {
  const keys = key.split(".");
  let value = translations[currentLang];
  for (const k of keys) {
    if (value && value[k] !== undefined) {
      value = value[k];
    } else {
      return key;
    }
  }
  return value;
}

function applyTranslations() {
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const key = el.getAttribute("data-i18n");
    el.textContent = t(key);
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
    const key = el.getAttribute("data-i18n-placeholder");
    el.placeholder = t(key);
  });
  document.documentElement.lang = currentLang;
}

function updateAuthTexts() {
  document.getElementById("title").textContent = isLogin ? t("loginTitle") : t("createAccount");
  document.getElementById("authBtn").textContent = isLogin ? t("signIn") : t("createAccount");
  document.getElementById("registerFields").style.display = isLogin ? "none" : "block";
  document.getElementById("toggleQuestion").textContent = isLogin
    ? t("dontHaveAccount")
    : t("alreadyHaveAccount");
  document.getElementById("toggleLink").textContent = isLogin ? t("register") : t("login");
}

// ── Theme Logic ──────────────────────────────────────────────────────────────
const themeToggle = document.getElementById("themeToggle");

function applyTheme(theme) {
  const isDark = theme === "dark";
  if (isDark) {
    document.body.classList.add("dark-mode");
    if (themeToggle) themeToggle.textContent = "☀️";
  } else {
    document.body.classList.remove("dark-mode");
    if (themeToggle) themeToggle.textContent = "🌙";
  }
}

if (themeToggle) {
  themeToggle.addEventListener("click", () => {
    const isDark = document.body.classList.toggle("dark-mode");
    themeToggle.textContent = isDark ? "☀️" : "🌙";
    chrome.storage.local.set({ theme: isDark ? "dark" : "light" });
  });
}

// ── Initialization (Sync Language, Theme, & Auth) ────────────────────────────
chrome.storage.local.get(["language", "token", "theme"], (data) => {
  // Sync Theme
  applyTheme(data.theme);

  // Sync Language
  if (data.language && ["en", "lt"].includes(data.language)) {
    currentLang = data.language;
  }
  applyTranslations();
  updateLanguageButtonText();

  // Sync Auth State
  isLogin = !data.token;
  updateAuthTexts();
});

// ── Toggle login/register ────────────────────────────────────────────────────
document.getElementById("toggleLink").addEventListener("click", () => {
  isLogin = !isLogin;
  updateAuthTexts();
});

// ── Language Toggle ──────────────────────────────────────────────────────────
const languageToggle = document.getElementById("languageToggle");

function updateLanguageButtonText() {
  if (languageToggle) {
    languageToggle.textContent = currentLang === "en" ? "LT" : "EN";
  }
}

languageToggle.addEventListener("click", () => {
  currentLang = currentLang === "en" ? "lt" : "en";
  chrome.storage.local.set({ language: currentLang });
  applyTranslations();
  updateLanguageButtonText();
  updateAuthTexts();
});

// ── External Change Listeners ────────────────────────────────────────────────
chrome.storage.onChanged.addListener((changes, namespace) => {
  if (changes.language) {
    currentLang = changes.language.newValue;
    applyTranslations();
    updateLanguageButtonText();
    updateAuthTexts();
  }
  if (changes.theme) {
    applyTheme(changes.theme.newValue);
  }
});

// ── Auth Submission ──────────────────────────────────────────────────────────
document.getElementById("authBtn").addEventListener("click", async () => {
  const email = document.getElementById("email").value;
  const password = document.getElementById("password").value;

  // Use production URL from main branch, fallback to local for dev if needed
  /*
  const url = isLogin 
    ? "http://api.healthfactchecker.site/auth/login" 
    : "http://api.healthfactchecker.site/auth/register";
    */
      const url = isLogin
    ? "http://localhost:8000/auth/login"
    : "http://localhost:8000/auth/register";

  let body;
  let headers = {};

  if (isLogin) {
    body = new URLSearchParams();
    body.append("username", email);
    body.append("password", password);
    headers["Content-Type"] = "application/x-www-form-urlencoded";
  } else {
    body = JSON.stringify({
      email,
      password,
      first_name: document.getElementById("firstName").value,
      last_name: document.getElementById("lastName").value,
    });
    headers["Content-Type"] = "application/json";
  }

  try {
    const response = await fetch(url, { method: "POST", headers, body });
    const data = await response.json();

    if (response.ok) {
		chrome.storage.local.set({ token: data.access_token, userEmail: email, userId: data.user_id }, () => {
        alert("Success!");
        window.close();
      });
    } else {
      console.log("Server rejected request:", data);
      alert("Error: " + (data.detail || "Check console for details"));
    }
  } catch (err) {
    console.error("Fetch failed entirely:", err);
    alert("Could not connect to server.");
  }
});
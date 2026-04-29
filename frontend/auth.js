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
  document.getElementById("title").textContent = isLogin ? t("login") : t("createAccount");
  document.getElementById("authBtn").textContent = isLogin ? t("signIn") : t("createAccount");
  document.getElementById("registerFields").style.display = isLogin ? "none" : "block";
  document.getElementById("toggleQuestion").textContent = isLogin
    ? t("dontHaveAccount")
    : t("alreadyHaveAccount");
  document.getElementById("toggleLink").textContent = isLogin ? t("register") : t("login");
}

// ── Theme & language sync ────────────────────────────────────────────────────
chrome.storage.local.get(["theme", "language", "token"], (data) => {
  if (data.theme === "dark") {
    document.body.classList.add("dark-mode");
  }
  if (data.language && ["en", "lt"].includes(data.language)) {
    currentLang = data.language;
  }
  applyTranslations();
  // If token exists, show logout mode (already logged in), else show login
  isLogin = !data.token;
  updateAuthTexts();
});

// ── Toggle login/register ────────────────────────────────────────────────────
document.getElementById("toggleLink").addEventListener("click", () => {
  isLogin = !isLogin;
  updateAuthTexts();
});

// ── Auth submit ──────────────────────────────────────────────────────────────
document.getElementById("authBtn").addEventListener("click", async () => {
  const email = document.getElementById("email").value;
  const password = document.getElementById("password").value;

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
      chrome.storage.local.set({ token: data.access_token, userEmail: email }, () => {
        alert("Login/Register Successful!");
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

let isLogin = true;

// Sync theme for auth page
chrome.storage.local.get("theme", (data) => {
  if (data.theme === "dark") {
    document.body.classList.add("dark-mode");
  }
});

document.getElementById('toggleLink').addEventListener('click', () => {
    isLogin = !isLogin;
    document.getElementById('title').innerText = isLogin ? "Login" : "Register";
    document.getElementById('authBtn').innerText = isLogin ? "Sign In" : "Create Account";
    document.getElementById('registerFields').style.display = isLogin ? "none" : "block";
    document.getElementById('toggleLink').innerText = isLogin ? "Don't have an account? Register" : "Already have an account? Login";
});

document.getElementById('authBtn').addEventListener('click', async () => {
    const email = document.getElementById('email').value;
    const password = document.getElementById('password').value;
    //local
    const url = isLogin ? "http://localhost:8000/auth/login" : "http://localhost:8000/auth/register";
    //server
    //const url = isLogin ? "http://api.healthfactchecker.site/auth/login" : "http://api.healthfactchecker.site/auth/register";

    // Submit logic (separate event listener)
    // Build the payload and headers based on whether it's login or registration
    let body;
    let headers = {};

    if (isLogin) {
        body = new URLSearchParams();
        body.append('username', email);
        body.append('password', password);
        headers['Content-Type'] = 'application/x-www-form-urlencoded';
    } else {
        body = JSON.stringify({
            email, password, 
            first_name: document.getElementById('firstName').value,
            last_name: document.getElementById('lastName').value
        });
        headers['Content-Type'] = 'application/json';
    }

    try {
        const response = await fetch(url, { method: 'POST', headers, body });
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
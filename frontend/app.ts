import { $ } from "./shared/dom";
import { createApi, asError } from "./shared/http";
import type { Language, Session, Stats } from "./shared/contracts";
import { words } from "./app/i18n";
import { createStatsRenderer } from "./app/rendering";
let language: Language =
  localStorage.getItem("hn_language") === "ru" ||
  (!localStorage.getItem("hn_language") && navigator.language.startsWith("ru"))
    ? "ru"
    : "en";
let state: Session = {},
  latest: Stats | null = null,
  refreshing = false;
const t = (key: string) => words[language][key] || key;
const { render, number, clearChart } = createStatsRenderer(t, () => language);
function translate() {
  document.documentElement.lang = language;
  document
    .querySelectorAll<HTMLElement>("[data-i18n]")
    .forEach((el) => (el.textContent = t(el.dataset.i18n || "")));
  $("language").textContent = language === "en" ? "RU" : "EN";
  $("auth-title").textContent = t(
    state.must_change && state.authenticated ? "change_title" : "login_title",
  );
  $("auth-copy").textContent = t(
    state.must_change && state.authenticated ? "change_copy" : "login_copy",
  );
  $("password-label").textContent = t(
    state.must_change && state.authenticated ? "new_password" : "password",
  );
  $("submit").textContent = t(
    state.must_change && state.authenticated ? "save" : "sign_in",
  );
  $("pie").setAttribute("aria-label", t("pie_label"));
  if (latest) render(latest);
  document.dispatchEvent(new Event("hn-language"));
}
const api = createApi(
  () => state,
  () => language,
  t,
  (fresh) => {
    // Transport recovery must not call view()/emit hn-session: the map owns a live draft.
    state = fresh;
  },
);
window.dashboardBridge = {
  version: 1,
  get session() {
    return state;
  },
  get language() {
    return language;
  },
  api,
  translate: t,
  replaceSession(session) {
    state = session;
    view();
  },
};
function view() {
  const allowed = !!state.authenticated && !state.must_change;
  $("auth").hidden = allowed;
  $("dashboard").hidden = !allowed;
  $("logout").hidden = !state.authenticated;
  const change = !!state.authenticated && !!state.must_change;
  $("confirm-group").hidden = !change;
  $("confirm").required = change;
  $("password").minLength = change ? 12 : 1;
  $("password").autocomplete = change ? "new-password" : "current-password";
  if (!allowed) {
    latest = null;
    $("legend").replaceChildren();
    $("total").textContent = "—";
    $("download").textContent = "—";
    $("upload").textContent = "—";
    clearChart();
  }
  translate();
  if (allowed) refresh();
  document.dispatchEvent(new Event("hn-session"));
}
async function refresh() {
  if (refreshing || !state.authenticated || state.must_change) return;
  refreshing = true;
  try {
    latest = await api("/api/stats");
    render(latest);
    $("refresh-error").textContent = "";
  } catch (caught) {
    const error = asError(caught);
    if (error.status === 401 || error.code === "password_change_required") {
      state = await api("/api/session");
      view();
      $("auth-error").textContent = t("session");
    } else {
      $("refresh-error").textContent = t("failure");
      $("live-state").textContent = t("stale");
      $("live-state").classList.add("amber");
      number("download", "—", language === "ru" ? "Мбит/с" : "Mbps");
      number("upload", "—", language === "ru" ? "Мбит/с" : "Mbps");
    }
  } finally {
    refreshing = false;
  }
}
$("language").addEventListener("click", () => {
  language = language === "en" ? "ru" : "en";
  localStorage.setItem("hn_language", language);
  translate();
});
$("auth-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("auth-error").textContent = "";
  const change = !!state.authenticated && !!state.must_change;
  if (change && $("password").value !== $("confirm").value) {
    $("auth-error").textContent = t("mismatch");
    return;
  }
  $("submit").disabled = true;
  try {
    state = await api(change ? "/api/password" : "/api/login", {
      password: $("password").value,
    });
    $("password").value = "";
    $("confirm").value = "";
    view();
  } catch (caught) {
    const error = asError(caught);
    $("auth-error").textContent = error.message;
  } finally {
    $("submit").disabled = false;
  }
});
$("logout").addEventListener("click", async () => {
  try {
    state = await api("/api/logout", {});
    view();
  } catch (caught) {
    const error = asError(caught);
    $("refresh-error").textContent = t("failure");
  }
});
translate();
api("/api/session")
  .then((data) => {
    state = data;
    view();
  })
  .catch(() => {
    $("auth-error").textContent = t("failure");
  });
setInterval(refresh, 5000);

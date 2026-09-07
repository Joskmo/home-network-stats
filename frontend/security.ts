import { text } from "./security/i18n";
import { $, element, button } from "./shared/dom";
import { getBridge, type Responses, type Payloads } from "./shared/contracts";
import { asError } from "./shared/http";
const bridge = getBridge();
const api = bridge.api;
const root = $("security");
let busy = false,
  generation = 0;
const tr = (key: string) => text[bridge.language][key];

function message(caught: unknown) {
  const error = asError(caught);
  $("security-message").textContent = error.retryAfter
    ? `${tr("retry")} ${error.retryAfter} ${tr("seconds")}`
    : error.message;
}
async function request<P extends keyof Responses>(
  path: P,
  payload?: Payloads[P],
) {
  try {
    return await api(path, payload);
  } catch (error) {
    message(error);
    throw error;
  }
}
async function load() {
  if (busy) return;
  const version = ++generation;
  root.hidden = !(
    bridge.session.password_authenticated || bridge.session.trusted_device
  );
  if (root.hidden) {
    root.replaceChildren();
    return;
  }
  busy = true;
  try {
    const data = await api("/api/trusted");
    if (version !== generation) return;
    root.replaceChildren(element("h2", tr("title")), element("p", tr("note")));
    const status = element("p");
    status.id = "security-message";
    status.setAttribute("role", "status");
    root.append(status);
    const label = element("label", tr("discovered"));
    label.htmlFor = "trusted-select";
    const select = document.createElement("select");
    select.id = "trusted-select";
    const candidates = data.devices.filter((row) => !row.trusted);
    for (const row of candidates) {
      const option = element("option", `${row.name} · ${row.ip}`);
      option.value = row.id;
      select.append(option);
    }
    if (!candidates.length) select.append(element("option", tr("empty")));
    select.disabled = !candidates.length;
    const add = button(tr("add"), async () => {
      add.disabled = true;
      try {
        await request("/api/trusted", {
          action: "add",
          device_id: select.value,
        });
        await load();
      } catch {
      } finally {
        add.disabled = !candidates.length;
      }
    });
    add.disabled = !candidates.length;
    root.append(label, select, add, button(tr("refresh"), load));
    const list = element("ul");
    if (!data.trusted.length) list.append(element("li", tr("none")));
    for (const row of data.trusted) {
      const li = element("li");
      li.append(element("span", `${row.name} · ${row.ip || tr("offline")}`));
      li.append(
        button(tr("remove"), async () => {
          if (!confirm(tr("confirm_remove"))) return;
          try {
            await request("/api/trusted", {
              action: "remove",
              device_id: row.id,
            });
            bridge.replaceSession(await api("/api/session"));
            await load();
          } catch {}
        }),
      );
      list.append(li);
    }
    root.append(list);
    if (bridge.session.trusted_device) {
      const details = element("details");
      details.append(element("summary", tr("recover")));
      const form = element("form");
      const password = element("input");
      password.id = "recover-password";
      password.type = "password";
      password.minLength = 12;
      password.maxLength = 256;
      password.required = true;
      password.autocomplete = "new-password";
      const again = password.cloneNode() as HTMLInputElement;
      again.id = "recover-confirm";
      const pl = element("label", tr("password"));
      pl.htmlFor = password.id;
      const cl = element("label", tr("confirm"));
      cl.htmlFor = again.id;
      const submit = element("button", tr("reset"));
      submit.type = "submit";
      form.append(pl, password, cl, again, submit);
      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        if (password.value !== again.value) {
          message(new Error(bridge.translate("mismatch")));
          return;
        }
        if (!confirm(tr("confirm_reset"))) return;
        submit.disabled = true;
        try {
          bridge.replaceSession(
            await request("/api/recover", { password: password.value }),
          );
          password.value = "";
          again.value = "";
          await load();
        } catch {
        } finally {
          submit.disabled = false;
        }
      });
      details.append(form);
      root.append(details);
    }
  } catch (error) {
    root.replaceChildren(element("p", tr("denied")));
  } finally {
    busy = false;
  }
}
document.addEventListener("hn-session", load);
document.addEventListener("hn-language", load);
load();

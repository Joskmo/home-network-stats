import type { Api, Trusted } from "./contracts";

// Compile-only regression: GET and POST on the same path differ on the wire.
async function trustedResponses(api: Api) {
  const list: Trusted = await api("/api/trusted");
  const explicitGet: Trusted = await api("/api/trusted", undefined);
  const result = await api("/api/trusted", {
    action: "add",
    device_id: "test-device",
  });
  const ok: true = result.ok;
  // @ts-expect-error POST does not return the trusted-device list.
  const invalidList: Trusted = result;
  // @ts-expect-error GET does not return a mutation acknowledgement.
  const invalidOk: true = list.ok;
  return { list, explicitGet, ok, invalidList, invalidOk };
}

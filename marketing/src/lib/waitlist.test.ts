import { afterEach, describe, expect, it, vi } from "vitest";
import { isValidEmail, submitWaitlist } from "./waitlist";

const ENDPOINT = "https://lists.example.test/api/public/subscription";

function withEndpoint(value: string | undefined) {
  vi.stubEnv("NEXT_PUBLIC_WAITLIST_ENDPOINT", value ?? "");
}

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("isValidEmail", () => {
  it.each(["a@b.co", "someone.else@firm.example", " padded@example.com "])("accepts %s", (value) =>
    expect(isValidEmail(value)).toBe(true));

  it.each([
    "",
    "no-at-sign",
    "no@tld",
    "two@@example.com",
    "spa ce@example.com",
  ])("rejects %s", (value) => expect(isValidEmail(value)).toBe(false));
});

describe("submitWaitlist", () => {
  it("reports not-configured when no endpoint is set, without calling the network", async () => {
    withEndpoint(undefined);
    const fetchImpl = vi.fn();

    const result = await submitWaitlist({ email: "a@b.co" }, fetchImpl as unknown as typeof fetch);

    expect(result).toEqual({ status: "not-configured" });
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("rejects a tripped honeypot before any network call", async () => {
    withEndpoint(ENDPOINT);
    const fetchImpl = vi.fn();

    const result = await submitWaitlist(
      { email: "a@b.co", honeypot: "http://spam.example" },
      fetchImpl as unknown as typeof fetch,
    );

    expect(result).toEqual({ status: "rejected" });
    // The point of the honeypot is that a bot costs us nothing.
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("posts the address when an endpoint is configured", async () => {
    withEndpoint(ENDPOINT);
    const fetchImpl = vi.fn().mockResolvedValue({ ok: true, status: 200 });

    const result = await submitWaitlist(
      { email: " a@b.co ", role: " counsel " },
      fetchImpl as unknown as typeof fetch,
    );

    expect(result).toEqual({ status: "ok" });
    const [url, init] = fetchImpl.mock.calls[0];
    expect(url).toBe(ENDPOINT);
    expect(JSON.parse(init.body)).toEqual({ email: "a@b.co", role: "counsel" });
  });

  it("treats a duplicate submission as success, not an error", async () => {
    // A 409 must not become a visible error: telling a stranger that an
    // address is already on the list is an enumeration oracle, and it is
    // baffling to someone who simply submitted twice.
    withEndpoint(ENDPOINT);
    const fetchImpl = vi.fn().mockResolvedValue({ ok: false, status: 409 });

    const result = await submitWaitlist({ email: "a@b.co" }, fetchImpl as unknown as typeof fetch);

    expect(result).toEqual({ status: "ok" });
  });

  it("surfaces a server failure", async () => {
    withEndpoint(ENDPOINT);
    const fetchImpl = vi.fn().mockResolvedValue({ ok: false, status: 500 });

    const result = await submitWaitlist({ email: "a@b.co" }, fetchImpl as unknown as typeof fetch);

    expect(result.status).toBe("error");
  });

  it("surfaces a network failure rather than throwing", async () => {
    withEndpoint(ENDPOINT);
    const fetchImpl = vi.fn().mockRejectedValue(new Error("offline"));

    const result = await submitWaitlist({ email: "a@b.co" }, fetchImpl as unknown as typeof fetch);

    expect(result.status).toBe("error");
  });

  it("omits an empty optional role rather than sending an empty string", async () => {
    withEndpoint(ENDPOINT);
    const fetchImpl = vi.fn().mockResolvedValue({ ok: true, status: 200 });

    await submitWaitlist({ email: "a@b.co", role: "   " }, fetchImpl as unknown as typeof fetch);

    expect(JSON.parse(fetchImpl.mock.calls[0][1].body)).toEqual({ email: "a@b.co" });
  });
});

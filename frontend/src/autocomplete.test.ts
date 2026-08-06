import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { attachDrugSuggestions } from "./autocomplete";
import * as api from "./api";

vi.mock("./api", () => ({
  searchDrugs: vi.fn(),
}));

describe("attachDrugSuggestions", () => {
  let input: HTMLInputElement;
  let datalist: HTMLDataListElement;

  beforeEach(() => {
    vi.useFakeTimers();
    input = document.createElement("input");
    datalist = document.createElement("datalist");
    document.body.append(input, datalist);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
    document.body.innerHTML = "";
  });

  it("does not query the API below the minimum query length", async () => {
    attachDrugSuggestions(input, datalist);
    input.value = "na";
    input.dispatchEvent(new Event("input"));
    await vi.advanceTimersByTimeAsync(500);

    expect(api.searchDrugs).not.toHaveBeenCalled();
  });

  it("debounces rapid typing into a single request for the final value", async () => {
    vi.mocked(api.searchDrugs).mockResolvedValue({
      data: { results: [], source: "cache" },
      elapsedMs: 10,
    });

    attachDrugSuggestions(input, datalist);
    input.value = "nap";
    input.dispatchEvent(new Event("input"));
    input.value = "napr";
    input.dispatchEvent(new Event("input"));

    await vi.advanceTimersByTimeAsync(299);
    expect(api.searchDrugs).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(50);
    expect(api.searchDrugs).toHaveBeenCalledTimes(1);
    expect(api.searchDrugs).toHaveBeenCalledWith("napr", 6);
  });

  it("populates the datalist with deduplicated suggestion names", async () => {
    vi.mocked(api.searchDrugs).mockResolvedValue({
      data: {
        results: [
          { nregistro: "1", nombre: "Naproxeno", pactivos: null, labtitular: null },
          { nregistro: "2", nombre: "Naproxeno", pactivos: null, labtitular: null },
        ],
        source: "cache",
      },
      elapsedMs: 10,
    });

    attachDrugSuggestions(input, datalist);
    input.value = "nap";
    input.dispatchEvent(new Event("input"));
    await vi.advanceTimersByTimeAsync(400);

    const options = datalist.querySelectorAll("option");
    expect(options).toHaveLength(1);
    expect(options[0]?.getAttribute("value")).toBe("Naproxeno");
  });

  it("clear() empties the datalist and cancels a pending lookup", async () => {
    vi.mocked(api.searchDrugs).mockResolvedValue({
      data: {
        results: [{ nregistro: "1", nombre: "Naproxeno", pactivos: null, labtitular: null }],
        source: "cache",
      },
      elapsedMs: 10,
    });

    const suggestions = attachDrugSuggestions(input, datalist);
    input.value = "nap";
    input.dispatchEvent(new Event("input"));
    suggestions.clear();

    await vi.advanceTimersByTimeAsync(400);

    expect(api.searchDrugs).not.toHaveBeenCalled();
    expect(datalist.innerHTML).toBe("");
  });

  it("does not surface a rejected suggestions request as an error to the caller", async () => {
    vi.mocked(api.searchDrugs).mockRejectedValue(new Error("network down"));

    attachDrugSuggestions(input, datalist);
    input.value = "nap";
    input.dispatchEvent(new Event("input"));

    await expect(vi.advanceTimersByTimeAsync(400)).resolves.not.toThrow();
    expect(datalist.innerHTML).toBe("");
  });
});

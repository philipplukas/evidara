import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Button } from "@/components/ui/button";

describe("Button consequence tier (ADR-0016)", () => {
  it("fires onClick immediately when tier is safe", () => {
    const onClick = vi.fn();
    render(
      <Button type="button" onClick={onClick}>
        Save
      </Button>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("does not fire onClick for notable until confirmed in popover", () => {
    const onClick = vi.fn();
    render(
      <Button
        type="button"
        tier="notable"
        confirmTitle="Proceed?"
        confirmLabel="Yes"
        cancelLabel="No"
        onClick={onClick}
      >
        Update
      </Button>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Update" }));
    expect(onClick).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Yes" }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("does not fire onClick for destructive until confirmed in dialog", () => {
    const onClick = vi.fn();
    render(
      <Button
        type="button"
        tier="destructive"
        confirmTitle="Delete item?"
        confirmLabel="Delete"
        cancelLabel="Cancel"
        onClick={onClick}
      >
        Remove
      </Button>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Remove" }));
    expect(onClick).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("notable cancel does not fire onClick", () => {
    const onClick = vi.fn();
    render(
      <Button
        type="button"
        tier="notable"
        confirmTitle="Proceed?"
        confirmLabel="Yes"
        cancelLabel="No"
        onClick={onClick}
      >
        Update
      </Button>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Update" }));
    fireEvent.click(screen.getByRole("button", { name: "No" }));
    expect(onClick).not.toHaveBeenCalled();
  });
});

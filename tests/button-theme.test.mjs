import assert from "node:assert/strict";
import test from "node:test";
import { normalizeHex, resolveThemeColors } from "../web/src/button-theme.js";

function luminance(hex) {
  const rgb = [1, 3, 5].map((index) => {
    const value = parseInt(hex.slice(index, index + 2), 16) / 255;
    return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
  });
  return rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722;
}

function contrast(first, second) {
  const values = [luminance(first), luminance(second)].sort((a, b) => b - a);
  return (values[0] + 0.05) / (values[1] + 0.05);
}

test("accepts only six-digit hex colors", () => {
  assert.equal(normalizeHex("#AA22FF"), "#aa22ff");
  for (const value of ["red", "#fff", "#ffffff; color:red", null]) {
    assert.equal(normalizeHex(value), null);
  }
});

test("every selected color yields readable control text and dark-surface accents", () => {
  for (const selected of [
    "#000000",
    "#101030",
    "#7777ff",
    "#ff0000",
    "#ffffff",
    "#ffff00",
    "#00ff00",
  ]) {
    const theme = resolveThemeColors(selected);
    assert.equal(theme.selected, selected);
    assert.ok(contrast(theme.accent, "#28282e") >= 4.5, selected);
    assert.ok(contrast(theme.accent, theme.ink) >= 4.5, selected);
  }
});

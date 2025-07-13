
window.electronAPI.onDisplayTooltip((event, { text, x, y }) => {
  const tooltip = document.getElementById('tooltip');
  tooltip.textContent = text;
  tooltip.style.left = `${x + 5}px`;
  tooltip.style.top = `${y + 5}px`;
  tooltip.style.opacity = 1;

  setTimeout(() => {
    tooltip.style.opacity = 0;
  }, 1000);
});

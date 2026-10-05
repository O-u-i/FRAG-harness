export function mount(element) {
  const title = document.createElement('h3');
  title.textContent = 'Selected local evidence';
  const text = document.createElement('p');
  text.textContent = 'In Harness, choose KB, a file and its excerpts. Each model stage needs a separate preview and approval.';
  element.replaceChildren(title, text);
  return () => element.replaceChildren();
}

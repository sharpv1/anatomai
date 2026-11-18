const paths = {
  practice: 'M5 19 19 5M5 5h14v14',
  percent: 'M5 19 19 5M7 5h.01M17 19h.01',
  check: 'm5 12 4 4L19 6',
  activity: 'M3 12h4l3-7 4 14 3-7h4',
  list: 'M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01',
};
export function LibraryIcon({ name }: { name: keyof typeof paths }) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name]} /></svg>;
}

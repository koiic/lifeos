import { copy } from '../../copy/en-GB';

/** Placeholder for the Today screen (T17 builds it); keeps the route lazy and real. */
export function TodayScreen() {
  return (
    <main>
      <h1>{copy.today.title}</h1>
    </main>
  );
}

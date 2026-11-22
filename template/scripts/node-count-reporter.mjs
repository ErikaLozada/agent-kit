// Node test reporter used by scripts/test.sh: writes how many test cases ran (passed, failed or todo).
// Skipped cases and describe() suites don't count, and console output can't change the number.
export default async function* count(source) {
  let ran = 0;
  for await (const event of source) {
    if ((event.type === 'test:pass' || event.type === 'test:fail') && !event.data.skip && event.data.details?.type !== 'suite') ran++;
  }
  yield `${ran}\n`;
}

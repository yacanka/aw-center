export function checkArrayEquals(array1: any[], array2: any[]) {
  if (!Array.isArray(array1) || !Array.isArray(array2)) {
    return false;
  }

  if (array1.length !== array2.length) {
    return false;
  }

  return array1.every((eleman, index) => eleman === array2[index]);
}

export function randomArray(n: number, min: number, max: number) {
  const lower = Math.min(min, max);
  const upper = Math.max(min, max);

  const array = [];
  for (let i = 0; i < n; i++) {
    const randomNum = Math.floor(Math.random() * (upper - lower + 1)) + lower;
    array.push(randomNum);
  }

  return array;
}
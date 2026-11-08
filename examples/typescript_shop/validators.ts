export function validateOrder(quantity: number): boolean {
  return Number.isInteger(quantity) && quantity >= 1 && quantity <= 100;
}

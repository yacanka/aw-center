/** New registration-number usernames use one Latin or Turkish letter and five digits. */
export const USERNAME_PATTERN = /^[A-Za-zÇĞİÖŞÜçğıöşü][0-9]{5}$/
export const USERNAME_MESSAGE =
  'Use one letter followed by exactly five digits (for example, U12345).'

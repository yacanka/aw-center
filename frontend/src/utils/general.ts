export function getType(value: any) {
    if (value === null) return 'null';
    return Object.prototype.toString.call(value).slice(8, -1).toLowerCase();
}

export function isPlainObject(obj: any) {
    return Object.prototype.toString.call(obj) === "[object Object]"
}

export function generateId(): string {
    return Math.random().toString(36).substring(2, 9)
}

export function nullCheck(
    value: any,
    options: {
        ignoreEmptyStrings?: boolean;
        ignoreEmptyArrays?: boolean;
        ignoreEmptyObjects?: boolean;
        ignoreZero?: boolean;
    } = {}
): boolean {
    const {
        ignoreEmptyStrings = false,
        ignoreEmptyArrays = false,
        ignoreEmptyObjects = false,
        ignoreZero = false,
    } = options;

    if (value == null) {
        return true;
    }

    if (typeof value === 'string') {
        if (ignoreEmptyStrings) return false;
        return value.trim() === '';
    }

    if (Array.isArray(value)) {
        if (ignoreEmptyArrays) return false;
        return value.length === 0;
    }

    if (typeof value === 'object') {
        if (ignoreEmptyObjects) return false;
        return Object.keys(value).length === 0;
    }

    if (typeof value === 'number') {
        if (ignoreZero) return false;
        return value === 0;
    }

    return false;
}

function getCssVariableValue(variableName: string) {
    const root = document.documentElement;
    const value = getComputedStyle(root).getPropertyValue(variableName).trim();

    if (!value) {
        console.warn(`CSS değişkeni bulunamadı: ${variableName}`);
        return null;
    }

    return value;
}

export function base64ToBytes(base64: string) {
    try {
        const byteCharacters = atob(base64);
        const byteArray = new Uint8Array(byteCharacters.length);
        for (let i = 0; i < byteCharacters.length; i++) {
            byteArray[i] = byteCharacters.charCodeAt(i);
        }
        return byteArray;
    } catch (error) {
        console.error("Error while converting Base64 to Bytes:", error);
        return new Uint8Array()
    }
}

export function sleep(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
}

export function binaryToBase64(data: ArrayBuffer | Uint8Array): string {
    const uint8 = data instanceof ArrayBuffer ? new Uint8Array(data) : data;
    return btoa(String.fromCharCode(...uint8));
};

export function findMostSimilarWord(word: string, wordList: Array<string>) {
    if (!word || !Array.isArray(wordList) || wordList.length === 0) {
        return null;
    }

    let minDistance = Infinity;
    let mostSimilar = null;

    wordList.forEach(candidate => {
        const distance = levenshteinDistance(word.toLowerCase(), candidate.toLowerCase());
        if (distance < minDistance) {
            minDistance = distance;
            mostSimilar = candidate;
        }
    });

    return { word: mostSimilar, distance: minDistance }
}

function levenshteinDistance(str1: string, str2: string) {
    const m = str1.length;
    const n = str2.length;

    const dp = Array(m + 1).fill(0).map(() => Array(n + 1).fill(0));

    for (let i = 0; i <= m; i++) dp[i][0] = i;
    for (let j = 0; j <= n; j++) dp[0][j] = j;

    for (let i = 1; i <= m; i++) {
        for (let j = 1; j <= n; j++) {
            const cost = str1[i - 1] === str2[j - 1] ? 0 : 1;
            dp[i][j] = Math.min(
                dp[i - 1][j] + 1,
                dp[i][j - 1] + 1,
                dp[i - 1][j - 1] + cost
            );
        }
    }

    return dp[m][n];
}
export function toCamelCase(str: string) {
    return str.replace(/[-_\s]+(.)?/g, (match, chr) => {
        return chr ? chr.toUpperCase() : '';
    });
}

export function toTitleCase(str: string) {
    return str.toLowerCase().split(' ').map(function (word) {
        return (word.charAt(0).toUpperCase() + word.slice(1));
    }).join(' ');
}

export function getFileNameAndExt(filename: string) {
    if (!filename || !filename.includes('.')) {
        return { name: filename, ext: '' };
    }

    const parts = filename.split('.');
    const name = parts.slice(0, -1).join('.');
    const ext = '.' + parts[parts.length - 1];

    return { name, ext };
}

export function isJsonString(str: string): boolean {
    if (typeof str !== 'string') return false;
    if (str.trim() === '') return false;

    try {
        JSON.parse(str);
        return true;
    } catch {
        return false;
    }
}
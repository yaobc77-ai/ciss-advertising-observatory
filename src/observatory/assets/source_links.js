var dagcomponentfuncs = window.dashAgGridComponentFunctions = window.dashAgGridComponentFunctions || {};
dagcomponentfuncs.SourceLink = function (props) {
    if (!props.enabled) return React.createElement('span', {className: 'source-muted'}, 'Links disabled');
    var valid = function (value) {
        try { var url = new URL(value); return (url.protocol === 'https:' || url.protocol === 'http:') ? url.href : null; }
        catch (error) { return null; }
    };
    var links = [];
    var original = valid(props.value);
    var archived = valid(props.data && props.data.archive_url);
    if (original) links.push(React.createElement('a', {key: 'original', href: original, target: '_blank', rel: 'noopener noreferrer'}, 'Original ↗'));
    if (archived) links.push(React.createElement('a', {key: 'archive', href: archived, target: '_blank', rel: 'noopener noreferrer'}, 'Archive ↗'));
    return React.createElement('span', {className: 'source-cell'}, links.length ? links : React.createElement('span', {className: 'source-muted'}, 'Unavailable'));
};

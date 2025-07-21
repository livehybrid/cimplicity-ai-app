const path = require('path');
const { merge: webpackMerge } = require('webpack-merge');
const baseComponentConfig = require('@splunk/webpack-configs/component.config').default;

module.exports = webpackMerge(baseComponentConfig, {
    mode: 'development',
    entry: {
        CiMplicityHome: path.join(__dirname, 'src/CiMplicityHome.jsx'),
    },
    output: {
        path: path.join(__dirname),
    },
});

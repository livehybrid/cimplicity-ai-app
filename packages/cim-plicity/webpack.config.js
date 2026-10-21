const fs = require('fs');
const path = require('path');
const CopyWebpackPlugin = require('copy-webpack-plugin');
const { merge: webpackMerge } = require('webpack-merge');
const baseConfig = require('@splunk/webpack-configs/base.config').default;

// Set up an entry config by iterating over the files in the pages directory.
const entries = fs
    .readdirSync(path.join(__dirname, 'src/main/webapp/pages'))
    .filter((pageFile) => !/^\./.test(pageFile))
    .reduce((accum, page) => {
        accum[page] = path.join(__dirname, 'src/main/webapp/pages', page);
        return accum;
    }, {});

module.exports = webpackMerge(baseConfig, {
    entry: entries,
    output: {
        path: path.join(__dirname, 'stage/appserver/static/pages/'),
        filename: '[name].js',
    },
    plugins: [
        new CopyWebpackPlugin({
            patterns: [
                {
                    from: path.join(__dirname, 'src/main/resources/splunk'),
                    to: path.join(__dirname, 'stage'),
                },
            ],
        }),
    ],
    optimization: {
        // webpack 5.110+ minifies CSS and HTML assets as well as JS, because
        // experiments.css and experiments.html both default to "auto". That
        // reaches the files CopyWebpackPlugin emits, which here is the whole
        // UCC-generated app, and both types must be shipped verbatim:
        //   - appserver/templates/*.html are Mako, not browser HTML. main.html
        //     carries `${json_decode(splunkd)}` inside a <script>, so the build
        //     dies with "Unexpected token: punc ({)" from terser.
        //   - the only CSS in the tree belongs to vendored third-party
        //     libraries (lib/sklearn/), which we ship unmodified.
        // JS minification is left on: that is unchanged from webpack 5.99 and
        // is what shrinks the page bundle.
        minimizeOptions: { css: false, html: false },
    },
    // eval-source-map ships eval() into the packaged bundle; dev only
    devtool: process.env.NODE_ENV === 'production' ? false : 'eval-source-map',
});

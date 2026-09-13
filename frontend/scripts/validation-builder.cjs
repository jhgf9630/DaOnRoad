const config = require('../package.json').build;
module.exports = { ...config, directories: { ...config.directories, output: '../dist-validation' } };

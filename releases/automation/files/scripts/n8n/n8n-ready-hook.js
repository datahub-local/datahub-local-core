const {
    dirname,
    resolve
} = require('path');
const Layer = require('router/lib/layer');
const assert = require("node:assert");
const {
    hash
} = require("bcryptjs");
const {
    issueCookie
} = require(resolve(dirname(require.resolve('n8n')), 'auth/jwt'))
const { exec } = require('child_process');

const {
    CUSTOM_INSTANCE_OWNER_EMAIL,
    CUSTOM_INSTANCE_OWNER_PASSWORD
} = process.env;

const ignoreAuthRegexp = /^\/(api|assets|healthz|metrics|rest|webhook)/;

module.exports = {
    n8n: {
        ready: [
            // Create Owner
            async function (server, config) {
                const logger = server.logger;

                logger.info('[OwnerSetup] Starting owner setup function');

                if (config.get("userManagement.isInstanceOwnerSetUp")) {
                    logger.info('[OwnerSetup] Instance owner is already set up, skipping setup');
                    return;
                }

                logger.info('[OwnerSetup] Attempting to set up owner with email: ' + CUSTOM_INSTANCE_OWNER_EMAIL);

                assert(CUSTOM_INSTANCE_OWNER_EMAIL, "Email missing from environment");
                assert(CUSTOM_INSTANCE_OWNER_PASSWORD, "Password missing from environment");

                try {
                    const owner = await this.dbCollections.User.findNonShellUser(CUSTOM_INSTANCE_OWNER_EMAIL);

                    if (!owner) {
                        logger.debug('[OwnerSetup] Found existing owner with ID: ' + owner.id);

                        const passwordHash = await hash(CUSTOM_INSTANCE_OWNER_PASSWORD, 10);
                        logger.debug('[OwnerSetup] Generated password hash for owner');

                        await this.dbCollections.User.save({
                            id: owner.id,
                            email: CUSTOM_INSTANCE_OWNER_EMAIL,
                            firstName: "no",
                            lastName: "name",
                            password: passwordHash,
                        });
                        logger.debug('[OwnerSetup] Updated owner details successfully');

                        await this.dbCollections.Settings.update(
                            {
                                key: "userManagement.isInstanceOwnerSetUp"
                            },
                            {
                                value: "true"
                            },);
                        logger.debug('[OwnerSetup] Updated settings to mark owner as set up');

                        config.set("userManagement.isInstanceOwnerSetUp", true);

                        logger.info('[OwnerSetup] Owner setup complete');
                    }
                } catch (error) {
                    logger.error('[OwnerSetup] Error during owner setup: ' + error);
                    throw error;
                }
            },

            // Add OAuth2-Proxy Middleware
            function (server, config) {
                const logger = server.logger;

                logger.info('[OAuth2Proxy] Starting OAuth2-Proxy Middleware setup');

                const {
                    stack
                } = server.app.router;
                logger.debug('[OAuth2Proxy] Current router stack length: ' + stack.length);

                stack.unshift(new Layer('/', {
                    strict: false,
                    end: false
                }, async (req, res, next) => {
                    logger.debug('[OAuth2Proxy] Middleware executing for URL: ' + req.url);
                    const {
                        CUSTOM_OAUTH2_PROXY_MIDDLEWARE_ENABLED
                    } = process.env;
                    logger.debug('[OAuth2Proxy] CUSTOM_OAUTH2_PROXY_MIDDLEWARE_ENABLED: ' + CUSTOM_OAUTH2_PROXY_MIDDLEWARE_ENABLED);

                    const middleware_enabled = CUSTOM_OAUTH2_PROXY_MIDDLEWARE_ENABLED?.toLowerCase() === 'true';
                    logger.debug('[OAuth2Proxy] Middleware enabled: ' + middleware_enabled);

                    if (!middleware_enabled || ignoreAuthRegexp.test(req.url)) {
                        logger.debug('[OAuth2Proxy] Skipping auth check - middleware disabled or URL is in ignore list');
                        return next();
                    }

                    const headers = Object.fromEntries(
                        Object.entries(req.headers).map(([k, v]) => [k.toLowerCase(), v])
                    );

                    const forwardedUser = headers['x-auth-request-user'];
                    logger.debug('[OAuth2Proxy] X-Auth-Request-User value: ' + forwardedUser);

                    if (!forwardedUser) {
                        logger.info('[OAuth2Proxy] Missing X-Auth-Request-User header, returning 401');

                        res.status(401).json({
                            code: 401,
                            message: 'Missing X-Auth-Request-User header'
                        });
                        return;
                    } else {
                        logger.debug('[OAuth2Proxy] Found forwarded user: ' + forwardedUser);

                        try {
                            const owner = await this.dbCollections.User.findNonShellUser(CUSTOM_INSTANCE_OWNER_EMAIL);

                            if (owner) {
                                logger.debug('[OAuth2Proxy] Found owner, attempting to issue cookie');

                                await issueCookie(res, owner);

                                logger.debug('[OAuth2Proxy] Cookie issued for owner');
                            } else {
                                logger.debug('[OAuth2Proxy] Owner not found');
                            }
                        } catch (error) {
                            logger.error('[OAuth2Proxy] Error finding owner: ' + error);
                        }

                        next()
                    }
                }));

                logger.debug('[OAuth2Proxy] Router stack after adding middleware: ' + stack.length);
                logger.info('[OAuth2Proxy] Configured OAuth2-Proxy Middleware successfully');
            },
            // Add InitCrendentials from json comming from env
            async function (server, config) {
                const logger = server.logger;

                logger.info('[InitCrendentials] Starting credentials import function');

                const {
                    CUSTOM_CREDENTIALS_FILE
                } = process.env;

                if (!CUSTOM_CREDENTIALS_FILE) {
                    logger.info('[InitCrendentials] No credentials to import, skipping setup');
                    return;
                }

                const currentCredentials = await this.dbCollections.Credentials.findAllPersonalCredentials();

                if (currentCredentials.length > 0) {
                    logger.info('[InitCrendentials] Credentials already initialized, skipping import');
                    return;
                }

                try {
                    const command = `n8n import:credentials --input ${CUSTOM_CREDENTIALS_FILE}`;

                    exec(command, (error, stdout, stderr) => {
                        if (error) {
                            logger.error(`[InitCrendentials] Error executing command: ${error.message}`);
                            throw error;
                        }
                        if (stderr) {
                            logger.warn(`[InitCrendentials] Command stderr: ${stderr}`);
                        }
                        logger.info(`[InitCrendentials] Command stdout: ${stdout}`);
                    });

                    await this.dbCollections.Settings.update(
                        {
                            key: "custom.isSecretsSetUp"
                        },
                        {
                            value: "true"
                        },);

                    logger.info('[InitCrendentials] Imported credentials successfully');
                } catch (error) {
                    logger.error('[InitCrendentials] Error during import: ' + error);
                }
            }
        ],
    },
};
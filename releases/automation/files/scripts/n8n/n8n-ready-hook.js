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
const ignoreAuthRegexp = /^\/(assets|healthz|webhook|rest)/;

module.exports = {
  n8n: {
      ready: [
          // Create Owner
          async function(server, config) {
                  const logger = server.logger;

                  logger.info('[Owner Setup] Starting owner setup function');

                  if (config.get("userManagement.isInstanceOwnerSetUp")) {
                      logger.info('[Owner Setup] Instance owner is already set up, skipping setup');
                      return;
                  }

                  const {
                      CUSTOM_INSTANCE_OWNER_EMAIL,
                      CUSTOM_INSTANCE_OWNER_PASSWORD
                  } = process.env;

                  logger.info('[Owner Setup] Attempting to set up owner with email: ' + CUSTOM_INSTANCE_OWNER_EMAIL);

                  assert(CUSTOM_INSTANCE_OWNER_EMAIL, "Email missing from environment");
                  assert(CUSTOM_INSTANCE_OWNER_PASSWORD, "Password missing from environment");

                  try {
                      const owner = await this.dbCollections.User.findOneOrFail({
                          where: {
                              role: "global:owner"
                          },
                      });
                      logger.debug('[Owner Setup] Found existing owner with ID: ' + owner.id);

                      const passwordHash = await hash(CUSTOM_INSTANCE_OWNER_PASSWORD, 10);
                      logger.debug('[Owner Setup] Generated password hash for owner');

                      await this.dbCollections.User.save({
                          id: owner.id,
                          email: CUSTOM_INSTANCE_OWNER_EMAIL,
                          firstName: "no",
                          lastName: "name",
                          password: passwordHash,
                      });
                      logger.debug('[Owner Setup] Updated owner details successfully');

                      await this.dbCollections.Settings.update(
                      {
                          key: "userManagement.isInstanceOwnerSetUp"
                      },
                      {
                          value: "true"
                      }, );
                      logger.debug('[Owner Setup] Updated settings to mark owner as set up');

                      config.set("userManagement.isInstanceOwnerSetUp", true);

                      logger.info('[Owner Setup] Owner setup complete');
                  } catch (error) {
                      logger.error('[Owner Setup] Error during owner setup: ' + error);
                      throw error;
                  }
              },

              // Add OAuth2-Proxy Middleware
              function(server, config) {
                  const logger = server.logger;

                  logger.info('[OAuth2 Proxy] Starting OAuth2-Proxy Middleware setup');

                  const {
                      stack
                  } = server.app.router;
                  logger.debug('[OAuth2 Proxy] Current router stack length: ' + stack.length);

                  stack.unshift(new Layer('/', {
                      strict: false,
                      end: false
                  }, async (req, res, next) => {
                      logger.debug('[OAuth2 Proxy] Middleware executing for URL: ' + req.url);
                      const {
                          CUSTOM_OAUTH2_PROXY_MIDDLEWARE_ENABLED
                      } = process.env;
                      logger.debug('[OAuth2 Proxy] CUSTOM_OAUTH2_PROXY_MIDDLEWARE_ENABLED: ' + CUSTOM_OAUTH2_PROXY_MIDDLEWARE_ENABLED);

                      const middleware_enabled = CUSTOM_OAUTH2_PROXY_MIDDLEWARE_ENABLED?.toLowerCase() === 'true';
                      logger.debug('[OAuth2 Proxy] Middleware enabled: ' + middleware_enabled);

                      if (!middleware_enabled || ignoreAuthRegexp.test(req.url)) {
                          logger.debug('[OAuth2 Proxy] Skipping auth check - middleware disabled or URL is in ignore list');
                          return next();
                      }

                      const headers = Object.fromEntries(
                          Object.entries(req.headers).map(([k, v]) => [k.toLowerCase(), v])
                      );

                      const forwardedUser = headers['x-auth-request-user'];
                      logger.debug('[OAuth2 Proxy] X-Auth-Request-User value: ' + forwardedUser);

                      if (!forwardedUser) {
                          logger.info('[OAuth2 Proxy] Missing X-Auth-Request-User header, returning 401');

                          res.status(401).json({
                              code: 401,
                              message: 'Missing X-Auth-Request-User header'
                          });
                          return;
                      } else {
                          logger.debug('[OAuth2 Proxy] Found forwarded user: ' + forwardedUser);

                          try {
                              const owner = await this.dbCollections.User.findOneBy({
                                  role: 'global:owner'
                              });

                              if (owner) {
                                  logger.debug('[OAuth2 Proxy] Found owner, attempting to issue cookie');

                                  await issueCookie(res, owner);

                                  logger.debug('[OAuth2 Proxy] Cookie issued for owner');
                              } else {
                                  logger.debug('[OAuth2 Proxy] Owner not found');
                              }
                          } catch (error) {
                              logger.error('[OAuth2 Proxy] Error finding owner: ' + error);
                          }

                          next()
                      }
                  }));

                  logger.debug('[OAuth2 Proxy] Router stack after adding middleware: ' + stack.length);
                  logger.info('[OAuth2 Proxy] Configured OAuth2-Proxy Middleware successfully');
              },
      ],
  },
};
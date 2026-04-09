use schemars::JsonSchema;
use serde::Deserialize;
use std::path::{Path, PathBuf};
use zed::settings::ContextServerSettings;
use zed_extension_api::{
    self as zed, serde_json, Command, ContextServerConfiguration, ContextServerId, Project, Result,
};

const CONTEXT_SERVER_ID: &str = "evidara-mcp";
const UV_COMMAND: &str = "uv";

struct EvidaraMcpExtension;

#[derive(Debug, Deserialize, JsonSchema)]
struct EvidaraMcpSettings {
    repo_root: String,
}

impl zed::Extension for EvidaraMcpExtension {
    fn new() -> Self {
        Self
    }

    fn context_server_command(
        &mut self,
        _context_server_id: &ContextServerId,
        project: &Project,
    ) -> Result<Command> {
        let settings = ContextServerSettings::for_project(CONTEXT_SERVER_ID, project)?;
        let Some(settings) = settings.settings else {
            return Err("missing `repo_root` setting".into());
        };
        let settings: EvidaraMcpSettings =
            serde_json::from_value(settings).map_err(|error| error.to_string())?;

        let repo_root = repo_root_path(&settings.repo_root)?;
        let mcp_directory = repo_root.join("tools").join("zed-evidara-mcp");

        Ok(Command {
            command: UV_COMMAND.to_string(),
            args: vec![
                "run".to_string(),
                "--directory".to_string(),
                path_string(&mcp_directory)?,
                "evidara-zed-mcp".to_string(),
            ],
            env: vec![("EVIDARA_REPO_ROOT".into(), path_string(&repo_root)?)],
        })
    }

    fn context_server_configuration(
        &mut self,
        _context_server_id: &ContextServerId,
        _project: &Project,
    ) -> Result<Option<ContextServerConfiguration>> {
        let installation_instructions =
            include_str!("../configuration/installation_instructions.md").to_string();
        let default_settings = include_str!("../configuration/default_settings.jsonc").to_string();
        let settings_schema = serde_json::to_string(&schemars::schema_for!(EvidaraMcpSettings))
            .map_err(|error| error.to_string())?;

        Ok(Some(ContextServerConfiguration {
            installation_instructions,
            default_settings,
            settings_schema,
        }))
    }
}

fn repo_root_path(value: &str) -> Result<PathBuf> {
    let path = PathBuf::from(value);
    if path.as_os_str().is_empty() {
        return Err("`repo_root` must not be empty".into());
    }
    Ok(path)
}

fn path_string(path: &Path) -> Result<String> {
    path.to_str()
        .map(ToOwned::to_owned)
        .ok_or_else(|| "path contains non-UTF-8 characters".to_string())
}

zed::register_extension!(EvidaraMcpExtension);

import pandas as pd

def filter_samples(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """
    Filter a dataframe by excluding control samples and samples marked for exclusion.
    """
    
    # Get the sample column name from the config
    sample_type = config.get("entity_type")
    sample_column = f"entity:{sample_type}_id"
    
    if not sample_column or sample_column not in df.columns:
        raise ValueError(f"Sample column '{sample_column}' not found in dataframe")
    
    filtered_df = df.copy()
    
    # Filter out control samples using fixed patterns (Ghost, Neg, Pos, PC, NC, H37)
    # https://github.com/theiagen/google-workflows/blob/main/california/tb/tb-transfer/mmpds-tb-dst-transfer.sh#L79
    control_patterns = "Ghost|Neg|Pos|PC|NC|H37"
    filtered_df = filtered_df[~filtered_df[sample_column].str.contains(control_patterns, 
                                                                      regex=True, 
                                                                      na=False)]
    
    # Filter out samples where CalTB-Net_Upload_Modifier is "exclude"
    upload_modifier_col = "CalTB-Net_Upload_Modifier"
    if upload_modifier_col in filtered_df.columns:
        filtered_df = filtered_df[filtered_df[upload_modifier_col] != "exclude"]
    
    return filtered_df